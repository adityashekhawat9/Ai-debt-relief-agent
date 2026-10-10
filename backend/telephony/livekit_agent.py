import os
import time
import asyncio
import logging
from typing import Optional
import re
import uuid

from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm
from livekit.agents.voice import Agent as VoiceAgent, AgentSession
from livekit.plugins import deepgram, elevenlabs, silero
from langchain_core.messages import HumanMessage

from core.config import get_settings
from services.ai.llm_engine import CloudLLMEngine
from services.telephony.vicidial_api import VICIdialBotClient
from conversation_engine.langgraph_dialogue import DialogueManager

logger = logging.getLogger("livekit_agent")

class SentenceChunker:
    """
    Buffers streaming tokens from LLM and yields speech-ready clauses at natural punctuation breaks.
    Strips internal protocol tags (<<TRANSFER>>, [DISPOSITION: ...]) so TTS never pronounces them.
    """
    def __init__(self):
        self.buffer = ""
        # Delimiters for natural human pauses: period, exclamation, question mark, comma, colon, semicolon, em-dash
        self.delimiter_regex = re.compile(r'([.!?,:;—]\s+)')

    def add_token(self, token: str) -> list[str]:
        self.buffer += token
        chunks = []
        while True:
            # First strip any complete tags so delimiters inside them (e.g. colon in [DISPOSITION: ...]) are never split
            self.buffer = re.sub(r'<<[^>]*>>|\[[^\]]*\]|<[^>]+>', '', self.buffer)

            # Avoid splitting if buffer currently ends in an unclosed tag like <<... or [...
            open_double = self.buffer.find("<<")
            if open_double != -1 and self.buffer.find(">>") == -1:
                break
                
            open_bracket = self.buffer.find("[")
            if open_bracket != -1 and self.buffer.find("]") == -1:
                break

            match = self.delimiter_regex.search(self.buffer)
            if not match:
                break
            end_pos = match.end()
            clause = self.buffer[:end_pos]
            self.buffer = self.buffer[end_pos:]
            cleaned = self.clean_text(clause)
            if cleaned:
                chunks.append(cleaned)
        return chunks

    def flush(self) -> list[str]:
        cleaned = self.clean_text(self.buffer)
        self.buffer = ""
        return [cleaned] if cleaned else []

    @staticmethod
    def clean_text(text: str) -> str:
        # Strip protocol tags before TTS synthesis
        text = re.sub(r'<<[^>]*>>', '', text)
        text = re.sub(r'\[[^\]]*\]', '', text)
        text = re.sub(r'<[^>]*>', '', text)
        text = re.sub(r'[<>]', '', text)
        return re.sub(r'\s+', ' ', text).strip()


class LangGraphLLMStream(llm.LLMStream):
    def __init__(self, llm_instance: "LangGraphLLM", chat_ctx: llm.ChatContext, tools: list, conn_options: "APIConnectOptions"):
        super().__init__(llm=llm_instance, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self.llm_instance = llm_instance

    async def _run(self) -> None:
        try:
            # Get the latest user message — robust parsing for SDK 1.1.x
            last_msg = None
            logger.info(f"[LiveKit] _run() called. chat_ctx has {len(self.chat_ctx.items)} items")
            
            for msg in reversed(self.chat_ctx.items):
                msg_role = getattr(msg, "role", None)
                msg_content = getattr(msg, "content", None)
                msg_type = getattr(msg, "type", "")
                logger.debug(f"[LiveKit] chat_ctx item: type={msg_type}, role={msg_role}, content_type={type(msg_content).__name__}")
                
                if msg_role == "user":
                    # Handle both string content and list-of-parts content
                    if isinstance(msg_content, str) and msg_content.strip():
                        last_msg = msg_content.strip()
                        break
                    elif isinstance(msg_content, list):
                        # Some SDK versions wrap content in a list of parts
                        for part in msg_content:
                            text = getattr(part, "text", None) or (part if isinstance(part, str) else None)
                            if text and isinstance(text, str) and text.strip():
                                last_msg = text.strip()
                                break
                        if last_msg:
                            break
                    
            # Yield empty delta to signal start
            if hasattr(llm, "Choice"):
                self._event_ch.send_nowait(llm.ChatChunk(choices=[llm.Choice(delta=llm.ChoiceDelta(content="", role="assistant"))]))
            else:
                self._event_ch.send_nowait(llm.ChatChunk(id=str(uuid.uuid4()), delta=llm.ChoiceDelta(content="", role="assistant")))
                
            if not last_msg:
                logger.warning("[LiveKit] _run(): No user message found in chat_ctx! Skipping LLM call.")
                return
                
            logger.info(f"[LiveKit] User said: {last_msg}")
            
            # Add user message to state
            self.llm_instance.state["messages"].append(HumanMessage(content=last_msg))

            chunker = SentenceChunker()
            chunks_sent = 0

            def emit_chunk(speech_text: str):
                nonlocal chunks_sent
                if not speech_text:
                    return
                chunks_sent += 1
                if hasattr(llm, "Choice"):
                    self._event_ch.send_nowait(
                        llm.ChatChunk(
                            choices=[
                                llm.Choice(
                                    delta=llm.ChoiceDelta(content=speech_text + " ", role="assistant")
                                )
                            ]
                        )
                    )
                else:
                    self._event_ch.send_nowait(
                        llm.ChatChunk(
                            id=str(uuid.uuid4()),
                            delta=llm.ChoiceDelta(content=speech_text + " ", role="assistant")
                        )
                    )

            async def stream_callback(token: str):
                clauses = chunker.add_token(token)
                for clause in clauses:
                    emit_chunk(clause)

            # Run DialogueManager with live incremental streaming to TTS
            try:
                session_id = self.llm_instance.ctx.room.name
                response_dict = await self.llm_instance.dialogue_manager.generate_reply(
                    self.llm_instance.state,
                    session_id=session_id,
                    stream_callback=stream_callback
                )
                self.llm_instance.state = response_dict

                # Flush any remaining tokens buffered during streaming
                for tail in chunker.flush():
                    emit_chunk(tail)

                response_text = ""
                if response_dict.get("messages"):
                    last_ai = response_dict["messages"][-1]
                    if last_ai.type == "ai":
                        response_text = last_ai.content

                # If no chunks were streamed (e.g. instant fast-path advance returned in <1ms),
                # send the clean response text immediately:
                if chunks_sent == 0 and response_text:
                    clean_full = SentenceChunker.clean_text(response_text)
                    if clean_full:
                        emit_chunk(clean_full)

            except Exception as e:
                logger.error(f"[LiveKit] DialogueManager Error: {e}", exc_info=True)
                response_text = "I'm having trouble processing that."
                emit_chunk(response_text)
                
            logger.info(f"[LiveKit] AI says: {response_text}")
            
            # Check for disconnect signals
            disconnect = False
            is_transfer = False
            disposition = None
            text_lower = response_text.lower()
            
            if "[transfer]" in text_lower or "<transfer>" in text_lower or "<<transfer>>" in text_lower:
                disconnect = True
                is_transfer = True
            elif "[end call]" in text_lower or "<end call>" in text_lower or "<<end call>>" in text_lower:
                disconnect = True
                
            # Parse disposition from AI output (e.g. [DISPOSITION: NQ])
            disp_match = re.search(r'\[DISPOSITION:\s*([A-Za-z_]+)\]', response_text)
            if disp_match:
                disposition = disp_match.group(1).upper()
                if "XFER" in disposition or "TRANSFER" in disposition or disposition == "QUALIFIED":
                    is_transfer = True
                    disconnect = True

            if self.llm_instance.state.get("fsm_state") == "TRANSFER_ROUTING":
                is_transfer = True
                disconnect = True
                
            if disconnect or disposition:
                asyncio.create_task(self.llm_instance.handle_disconnect(disposition=disposition, is_transfer=is_transfer))
            
        except Exception as e:
            logger.error(f"[LiveKit] CRITICAL: _run() crashed: {e}", exc_info=True)


class LangGraphLLM(llm.LLM):
    def __init__(self, dialogue_manager: DialogueManager, ctx: JobContext):
        super().__init__()
        self.dialogue_manager = dialogue_manager
        self.ctx = ctx
        self.agent = None # will be set in entrypoint
        self.state = {
            "messages": [],
            "fsm_state": "START",
            "qualification_answers": {},
            "objection_count": 0,
            "dnc_count": 0,
            "intent": None,
            "script_step": 1,
            "lead_first_name": "LocalUser",
            "nlu_response": None,
            "sentiment": "NEUTRAL"
        }
        
    def chat(self, *, chat_ctx: llm.ChatContext, tools: list = None, conn_options = None, **kwargs) -> LangGraphLLMStream:
        from livekit.agents import APIConnectOptions
        conn_opts = conn_options if conn_options is not None else APIConnectOptions()
        return LangGraphLLMStream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_opts)
        
    async def handle_disconnect(self, disposition: str = None, is_transfer: bool = False):
        # Wait a few seconds for the agent to finish speaking
        await asyncio.sleep(4)
        
        sip_meta = self.state.get("sip_metadata", {}) or {}
        settings = get_settings()

        # Extract Asterisk channel
        channel = (
            sip_meta.get("x-asterisk-channel")
            or sip_meta.get("x-channel")
            or sip_meta.get("sip.header.x-channel")
            or sip_meta.get("sip.header.x-asterisk-channel")
            or sip_meta.get("channel")
            or sip_meta.get("sip.callid")
        )

        # Extract Asterisk UNIQUEID
        unique_id = (
            sip_meta.get("x-asterisk-uniqueid")
            or sip_meta.get("x-uniqueid")
            or sip_meta.get("sip.header.x-uniqueid")
            or sip_meta.get("sip.header.x-asterisk-uniqueid")
            or sip_meta.get("uniqueid")
            or (getattr(getattr(self.ctx, "room", None), "name", None))
        )

        # 1. Vicidial Call Transfer & Hangup Bot API (AmiHangup.php)
        bot_api_url = getattr(settings, "VICIDIAL_BOT_API_URL", None)
        if channel and unique_id and bot_api_url:
            try:
                bot_client = VICIdialBotClient()
                if is_transfer:
                    comment = f"AI Transfer: disposition={disposition or 'QUALIFIED'}"
                    logger.info(f"[LiveKit] Triggering Vicidial AmiHangup TRANSFER for channel={channel}, unique_id={unique_id}")
                    resp = await bot_client.transfer_call(
                        channel=str(channel),
                        unique_id=str(unique_id),
                        comment=comment,
                    )
                    logger.info(f"[LiveKit] Vicidial Bot API TRANSFER result: {resp}")
                else:
                    comment = f"AI Hangup: disposition={disposition or 'NORMAL'}"
                    logger.info(f"[LiveKit] Triggering Vicidial AmiHangup HANGUP for channel={channel}, unique_id={unique_id}")
                    resp = await bot_client.hangup_call(
                        channel=str(channel),
                        unique_id=str(unique_id),
                        comment=comment,
                    )
                    logger.info(f"[LiveKit] Vicidial Bot API HANGUP result: {resp}")
                await bot_client.close()
            except Exception as e:
                logger.error(f"[LiveKit] Error calling Vicidial Bot API: {e}", exc_info=True)
        else:
            logger.warning(
                f"[LiveKit] Vicidial Bot API skipped (channel={channel}, unique_id={unique_id}, bot_api_url={bot_api_url})"
            )

        # 2. Trigger webhook for LMS if configured
        if disposition:
            logger.info(f"Triggering webhook for disposition: {disposition}")
            lead_id = sip_meta.get("lead_id") or "livekit_unknown"
            
            if settings.OLIVIA_WEBHOOK_URL:
                payload = {
                    "lead_id": lead_id,
                    "disposition": disposition,
                    "timestamp": time.time(),
                    "fsm_state": self.state.get("fsm_state", "QUALIFICATION"),
                }
                import httpx
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(settings.OLIVIA_WEBHOOK_URL, json=payload)
                        logger.info(f"Olivia Webhook response: {resp.status_code}")
                except Exception as e:
                    logger.error(f"Failed to hit Olivia Webhook: {e}")
            else:
                logger.warning("OLIVIA_WEBHOOK_URL not set in .env. Skipping webhook.")
            
        logger.info("Disconnecting LiveKit Room")
        await self.ctx.disconnect()


async def entrypoint(ctx: JobContext):
    logger.info(f"Connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Initialize Backend Services
    settings = get_settings()
    llm_engine = CloudLLMEngine()
    
    # Lazy load vector services
    try:
        from services.rag.qdrant_client import QdrantService
        from services.rag.embedder import EmbedderService
        qdrant = QdrantService()
        embedder = EmbedderService()
    except ImportError:
        qdrant = None
        embedder = None
        
    dialogue_manager = DialogueManager(
        llm_engine=llm_engine,
        qdrant_service=qdrant,
        embedder_service=embedder
    )
    
    # Start the conversation with an initial trigger
    # Wait for participant to connect
    participant = await ctx.wait_for_participant()
    logger.info(f"Participant connected: {participant.identity}")
    
    # Log standard SIP attributes
    attrs = getattr(participant, "attributes", {}) or {}
    logger.info(f"Caller SIP Attributes: {attrs}")
    
    # Retrieve all raw incoming SIP headers directly via LiveKit RPC
    raw_sip_headers = {}
    try:
        if hasattr(ctx.room, "local_participant") and ctx.room.local_participant:
            rpc_payload = await ctx.room.local_participant.perform_rpc(
                destination_identity=participant.identity,
                method="lk.sip.GetRemoteHeaders",
                payload="{}",
            )
            if rpc_payload:
                import json
                parsed_data = json.loads(rpc_payload)
                raw_sip_headers = parsed_data.get("headers", {})
                logger.info(f"Raw SIP Headers received via RPC: {raw_sip_headers}")
    except Exception as e:
        logger.warning(f"Could not fetch raw SIP headers via lk.sip.GetRemoteHeaders: {e}")

    # Combine all incoming attributes and headers into one dictionary
    combined_data = {}
    for k, v in attrs.items():
        combined_data[k] = v
        combined_data[k.lower()] = v
    for k, v in raw_sip_headers.items():
        combined_data[k] = v
        combined_data[k.lower()] = v

    logger.info(f"All incoming caller data: {combined_data}")

    custom_llm = LangGraphLLM(dialogue_manager=dialogue_manager, ctx=ctx)
    custom_llm.state["sip_metadata"] = combined_data

    # Extract caller first name from any available header or attribute
    first_name = (
        combined_data.get("x-first-name")
        or combined_data.get("x-firstname")
        or combined_data.get("first_name")
        or combined_data.get("firstname")
        or combined_data.get("name")
        or combined_data.get("sip.header.x-first-name")
    )
    if first_name:
        custom_llm.state["lead_first_name"] = str(first_name).strip().capitalize()
        logger.info(f"Lead first name initialized to: {custom_llm.state['lead_first_name']}")

    agent_kwargs = {
        "vad": silero.VAD.load(
            min_speech_duration=0.08, # Fast detection of human speech onset
            min_silence_duration=0.28, # Snappy end-of-speech silence detection
        ),
        "stt": deepgram.STT(model="nova-2-phonecall"),
        "llm": custom_llm,
        "tts": elevenlabs.TTS(
            model="eleven_turbo_v2_5", 
            voice_id="uYXf8XasLslADfZ2MB4u",
            api_key=os.environ.get("ELEVENLABS_API_KEY", "")
        ),
        "instructions": "",
        "allow_interruptions": True,
    }

    # Pass endpointing delays only if supported by the installed livekit-agents version
    import inspect
    agent_sig = inspect.signature(VoiceAgent.__init__).parameters
    if "min_endpointing_delay" in agent_sig:
        agent_kwargs["min_endpointing_delay"] = 0.25
    if "max_endpointing_delay" in agent_sig:
        agent_kwargs["max_endpointing_delay"] = 0.70

    agent = VoiceAgent(**agent_kwargs)
    
    custom_llm.agent = agent
    
    # Start the agent session
    session = AgentSession()
    await session.start(agent, room=ctx.room)
    
    # --- INSTANT GREETING (avoids 10+ second LLM cold start silence) ---
    # Send a hardcoded opening line immediately so the caller hears something right away.
    # The LLM dialogue state is warmed up in the background so it's ready for the caller's reply.
    INSTANT_GREETING = (
        "Hi, this is Angela with US Debt Relief on a recorded line. "
        "I'm reaching out because you might be eligible for a new relief program "
        "that significantly reduces credit card debt. "
        "Just to get an idea of where you're starting from — "
        "do you have over seven thousand dollars in total unsecured debt right now?"
    )
    
    logger.info(f"[LiveKit] Sending instant greeting immediately to avoid silence timeout.")
    
    # Speak the greeting instantly — no LLM call needed
    await session.say(INSTANT_GREETING, allow_interruptions=True)
    
    # Warm up the LLM state in the background so it's ready for the caller's first reply
    async def _warmup_llm_state():
        try:
            custom_llm.state["messages"].append(HumanMessage(content="[SYSTEM: Agent just said the opening greeting. Wait for caller response.]"))
            from langchain_core.messages import AIMessage
            custom_llm.state["messages"].append(AIMessage(content=INSTANT_GREETING))
            logger.info("[LiveKit] LLM state warmed up with greeting context.")
        except Exception as e:
            logger.error(f"[LiveKit] LLM state warmup failed: {e}")
    
    asyncio.create_task(_warmup_llm_state())


def start_livekit_worker():
    """Start the LiveKit worker in the current process"""
    cli.run_app(
        WorkerOptions(
            agent_name="debt-relief-agent",
            entrypoint_fnc=entrypoint,
        )
    )

if __name__ == "__main__":
    start_livekit_worker()
