import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID

from core.config import get_settings
from core.logging import get_logger
from core.exceptions import CallTimerExpiredError, AppException
from core.metrics import ACTIVE_CALLS, CALL_DURATION
from services.telephony.audiosocket import AudioSocketServer, AudioSocketSession
from conversation_engine.session_manager import SessionManager
from conversation_engine.langgraph_dialogue import DialogueManager, DialogueState
from services.compliance.dnc_checker import DNCChecker
from langchain_core.messages import HumanMessage

logger = get_logger(__name__)

class CallPhase(str, Enum):
    """High-level call lifecycle phases (not FSM states)."""
    INITIATING   = "initiating"
    CONNECTED    = "connected"
    AI_ACTIVE    = "ai_active"
    TRANSFERRING = "transferring"
    ENDING       = "ending"
    ENDED        = "ended"

@dataclass
class CallContext:
    """All runtime state for a single active call."""
    call_id: str
    lead_id: str
    channel_uuid: str        # AudioSocket channel UUID from Asterisk
    asterisk_channel: str    # e.g. 'PJSIP/+15551234567-00000001'
    phone: str
    country: str             # 'US' | 'IN'
    phase: CallPhase = CallPhase.INITIATING
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    answered_at: datetime | None = None
    timer_task: asyncio.Task | None = None
    pipeline_task: asyncio.Task | None = None
    is_active: bool = True

from services.telephony.vicidial_api import VICIdialAPI, VICIdialBotClient
from services.telephony.asterisk_ari import AsteriskARI
from models.database.qualification import AgentTransfer

class CallOrchestrator:
    """Per-call async controller."""
    
    def __init__(
        self,
        call_id: str,
        lead_id: str,
        channel_uuid: str,
        asterisk_channel: str,
        phone: str,
        country: str,
        audiosocket_server: AudioSocketServer,
        session_manager: SessionManager,
        db_session,            # AsyncSession — injected
        redis_client,          # aioredis.Redis — injected
        vicidial_client: VICIdialAPI = None,
        ari_client: AsteriskARI = None,
    ) -> None:
        self._context = CallContext(
            call_id=call_id,
            lead_id=lead_id,
            channel_uuid=channel_uuid,
            asterisk_channel=asterisk_channel,
            phone=phone,
            country=country,
        )
        self._audiosocket = audiosocket_server
        self._session_manager = session_manager
        self._db_session = db_session
        self._redis_client = redis_client
        self._vicidial_client = vicidial_client
        self._ari_client = ari_client
        
        # Initialize DialogueManager (with stub LLM engine)
        self._dialogue_manager = DialogueManager(llm_engine=None)
        self._fsm_state = "QUALIFICATION"
        self._dialogue_state: DialogueState = {
            "messages": [],
            "fsm_state": self._fsm_state,
            "qualification_answers": {},
            "objection_count": 0,
            "intent": None
        }
    
    async def start(self) -> None:
        """Begin orchestrating the call."""
        await self._session_manager.create_session(self._context.call_id)
        
        logger.info("Call started", call_id=self._context.call_id)
        self._context.answered_at = datetime.now(timezone.utc)
        ACTIVE_CALLS.inc()
        
        self._context.phase = CallPhase.AI_ACTIVE
        self._context.timer_task = asyncio.create_task(self._call_timer())
        self._context.pipeline_task = asyncio.create_task(self._ai_pipeline_loop())
    
    async def _call_timer(self) -> None:
        """5-minute hard call timer."""
        settings = get_settings()
        warning_at = settings.MAX_CALL_DURATION_SECONDS - settings.CALL_TIMER_WARNING_SECONDS
        
        try:
            await asyncio.sleep(warning_at)
            await self._on_timer_warning()
            await asyncio.sleep(settings.CALL_TIMER_WARNING_SECONDS)
            await self._on_timer_expired()
        except asyncio.CancelledError:
            pass
    
    async def _on_timer_warning(self) -> None:
        """Called at 4:30. Signal FSM to transition to POLITE_CLOSE."""
        logger.warning("Call timer warning", call_id=self._context.call_id)
        # Update Redis session fsm_state to POLITE_CLOSE
        # Stub logic
        pass
    
    async def _on_timer_expired(self) -> None:
        """Called at 5:00. Hard limit reached."""
        logger.warning("Call timer expired", call_id=self._context.call_id)
        await asyncio.sleep(1.0)
        await self.end_call(reason='timer_expired')
    
    async def _ai_pipeline_loop(self) -> None:
        """Main AI pipeline loop for the call."""
        logger.info("AI pipeline loop started (Phase 3 Stream C)", call_id=self._context.call_id)
        
        session = self._audiosocket.get_session(self._context.channel_uuid)
        if session is None:
            logger.error("AudioSocket session not found", channel_uuid=self._context.channel_uuid)
            return
        
        try:
            while self._context.is_active:
                chunk = await self._audiosocket.get_audio_chunk(
                    self._context.channel_uuid,
                    timeout=1.0,
                )
                if chunk:
                    # 1. Got audio chunk
                    
                    # 2. STT (stubbed)
                    user_text = "I am interested" # stubbed STT result
                    logger.debug(f"STT recognized: {user_text}", call_id=self._context.call_id)
                    
                    # Log user utterance
                    await self._session_manager.append_transcript(
                        call_id=self._context.call_id,
                        speaker="user",
                        text=user_text,
                        fsm_state=self._fsm_state,
                        confidence=1.0
                    )
                    
                    # 3. OptOutDetector (stubbed)
                    if "stop" in user_text.lower() or "do not call" in user_text.lower():
                        await self.handle_opt_out()
                        break
                    
                    # 4. FSM advance_state (stubbed)
                    if self._fsm_state == "TRANSFER_ROUTING":
                        await self.handle_transfer()
                        break
                    
                    if self._fsm_state in ["QUALIFICATION", "OBJECTION"]:
                        # 5. LangGraph DialogueManager
                        self._dialogue_state["messages"] = list(self._dialogue_state["messages"]) + [HumanMessage(content=user_text)]
                        new_state = await self._dialogue_manager.generate_reply(self._dialogue_state)
                        self._dialogue_state = new_state
                        
                        reply_msg = new_state["messages"][-1].content if new_state["messages"] else "Hello."
                        logger.debug(f"AI reply: {reply_msg}", call_id=self._context.call_id)
                        
                        # Log AI utterance
                        await self._session_manager.append_transcript(
                            call_id=self._context.call_id,
                            speaker="ai",
                            text=reply_msg,
                            fsm_state=self._fsm_state,
                            confidence=1.0
                        )
                        
                        # Check if LangGraph requested a transfer
                        if new_state.get("fsm_state") == "TRANSFER_ROUTING":
                            self._fsm_state = "TRANSFER_ROUTING"
                        elif new_state.get("fsm_state") == "DNC":
                            self._fsm_state = "DNC"
                            if hasattr(self, '_context') and hasattr(self._context, 'phone'):
                                asyncio.create_task(self._dnc_checker.trigger_external_dnc_webhook(self._context.phone))
                        elif new_state.get("fsm_state") == "VOICEMAIL":
                            self._fsm_state = "VOICEMAIL"
                            break
                            
                        # 6. TTS (stubbed)
                        tts_audio_chunk = chunk # echo chunk to simulate TTS
                        
                        # 7. Send audio back
                        await self._audiosocket.send_audio(self._context.channel_uuid, tts_audio_chunk)
                        logger.debug("Audio sent (simulated TTS)", call_id=self._context.call_id)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("AI pipeline error", call_id=self._context.call_id, exc_info=e)

    async def handle_transfer(self) -> None:
        """Execute the live VICIdial data push and Asterisk call transfer."""
        logger.info("Executing live transfer to human closer", call_id=self._context.call_id)
        self._context.phase = CallPhase.TRANSFERRING

        # 1. Compile the context from the dialogue state
        answers = self._dialogue_state.get("qualification_answers", {})
        messages = self._dialogue_state.get("messages", [])
        
        summary_lines = ["[AI QUALIFIED]"]
        for q, a in answers.items():
            summary_lines.append(f"{q}: {a}")
        
        # Grab the last 4 messages for quick context
        recent_msgs = messages[-4:] if len(messages) >= 4 else messages
        if recent_msgs:
            summary_lines.append("\n-- Recent Transcript --")
            for m in recent_msgs:
                speaker = "User" if isinstance(m, HumanMessage) else "AI"
                summary_lines.append(f"{speaker}: {m.content}")
                
        compiled_summary = "\n".join(summary_lines)

        # 2. VICIdial Data Push
        if self._vicidial_client:
            try:
                # Push the compiled summary into the lead's comments
                await self._vicidial_client.update_lead(
                    lead_id=self._context.lead_id,
                    custom_fields={"comments": compiled_summary}
                )
                logger.debug("Successfully pushed data to VICIdial", call_id=self._context.call_id)
            except Exception as e:
                logger.error("Failed to push data to VICIdial", exc_info=e)
        
        # 3. Database Logging
        if self._db_session:
            try:
                transfer_log = AgentTransfer(
                    call_id=self._context.call_id,
                    destination_agent_group="CLOSERS", # Placeholder
                    transcript_summary=compiled_summary
                )
                self._db_session.add(transfer_log)
                await self._db_session.commit()
            except Exception as e:
                logger.error("Failed to log transfer to DB", exc_info=e)

        # 4. Asterisk Call Routing
        if self._ari_client:
            try:
                # Redirect the channel to the VICIdial Ingroup (e.g., PJSIP/CLOSERS)
                target_endpoint = "PJSIP/CLOSERS" # Should be pulled from config in prod
                await self._ari_client.redirect_channel(
                    channel_id=self._context.asterisk_channel,
                    endpoint=target_endpoint
                )
                logger.info("Redirected Asterisk channel to VICIdial Ingroup", target=target_endpoint)
            except Exception as e:
                logger.error("Failed to redirect Asterisk channel", exc_info=e)

        # 5. Vicidial Bot API Call Transfer (AmiHangup.php)
        try:
            bot_client = VICIdialBotClient()
            channel = self._context.asterisk_channel
            unique_id = self._context.channel_uuid or self._context.call_id
            if channel:
                logger.info("Triggering Vicidial Bot API transfer", channel=channel, unique_id=unique_id)
                await bot_client.transfer_call(
                    channel=channel,
                    unique_id=unique_id,
                    comment="Transferred to in-group real agent",
                )
            await bot_client.close()
        except Exception as e:
            logger.error("Failed to execute Vicidial Bot API transfer", exc_info=e)

        # The AI is done, end the AI portion of the call
        await self.end_call(reason="transferred", outcome="qualified")
    
    async def end_call(
        self,
        reason: str = "completed",
        outcome: str | None = None,
    ) -> None:
        """Gracefully end the call."""
        if not self._context.is_active:
            return
            
        self._context.is_active = False
        
        if self._context.timer_task:
            self._context.timer_task.cancel()
        if self._context.pipeline_task:
            self._context.pipeline_task.cancel()
            
        try:
            await self._audiosocket.send_hangup(self._context.channel_uuid)
        except Exception:
            pass

        # Vicidial Bot API Hangup (AmiHangup.php) when not already transferred
        if reason != "transferred":
            try:
                bot_client = VICIdialBotClient()
                channel = self._context.asterisk_channel
                unique_id = self._context.channel_uuid or self._context.call_id
                if channel:
                    logger.info("Triggering Vicidial Bot API hangup", channel=channel, unique_id=unique_id)
                    await bot_client.hangup_call(
                        channel=channel,
                        unique_id=unique_id,
                        comment=f"Call ended: {reason}",
                    )
                await bot_client.close()
            except Exception as e:
                logger.error("Failed to execute Vicidial Bot API hangup", exc_info=e)
            
        await self._flush_transcript_to_db()
        await self._session_manager.delete_session(self._context.call_id)
        
        ACTIVE_CALLS.dec()
        CALL_DURATION.observe(self.duration_seconds)
        
        logger.info("Call ended", call_id=self._context.call_id, duration=self.duration_seconds, reason=reason)
    
    async def _flush_transcript_to_db(self) -> None:
        """Read transcript from Redis and bulk-insert into PostgreSQL."""
        if not self._db_session:
            logger.warning("No DB session, skipping transcript flush", call_id=self._context.call_id)
            return
            
        try:
            transcript_entries = await self._session_manager.get_transcript(self._context.call_id)
            if not transcript_entries:
                logger.debug("No transcript entries to flush", call_id=self._context.call_id)
                return
                
            from models.database.transcript import Transcript
            from dateutil.parser import isoparse
            import uuid
            
            db_transcripts = []
            call_uuid = uuid.UUID(self._context.call_id)
            
            for entry in transcript_entries:
                spoken_at_str = entry.get("spoken_at")
                if spoken_at_str:
                    try:
                        spoken_at_dt = isoparse(spoken_at_str)
                    except Exception:
                        spoken_at_dt = datetime.now(timezone.utc)
                else:
                    spoken_at_dt = datetime.now(timezone.utc)
                
                db_transcripts.append(
                    Transcript(
                        call_id=call_uuid,
                        speaker=entry.get("speaker", "unknown"),
                        text=entry.get("text", ""),
                        fsm_state=entry.get("fsm_state"),
                        confidence=entry.get("confidence", 1.0),
                        spoken_at=spoken_at_dt
                    )
                )
                
            self._db_session.add_all(db_transcripts)
            await self._db_session.commit()
            logger.info("Flushed transcript to DB", call_id=self._context.call_id, count=len(db_transcripts))
        except Exception as e:
            logger.error("Failed to flush transcript to DB", call_id=self._context.call_id, exc_info=e)
            if self._db_session:
                await self._db_session.rollback()
    
    async def handle_opt_out(self) -> None:
        """Handle opt-out detected during call."""
        logger.info("Opt-out handled", call_id=self._context.call_id)
        await self.end_call(reason="opt_out", outcome="opt_out")
    
    @property
    def is_active(self) -> bool:
        """True if this call is still in progress."""
        return self._context.is_active
    
    @property
    def call_id(self) -> str:
        return self._context.call_id
    
    @property  
    def duration_seconds(self) -> int:
        """Elapsed call duration since answered_at."""
        if self._context.answered_at is None:
            return 0
        return int((datetime.now(timezone.utc) - self._context.answered_at).total_seconds())
