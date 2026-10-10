"""
AMI Event Handler — processes Asterisk call events and persists state to PostgreSQL.

Registered event handlers:
  Dial        → call initiated
  DialEnd     → call answered or no-answer
  Hangup      → call ended, compute duration
  AgentConnect → agent connected (post-transfer)
  AgentComplete→ agent call complete
"""
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select

from core.logging import get_logger
from models.database.call import Call
from models.database.audit import AuditLog
from services.telephony.asterisk_ami import AsteriskAMI, AMIEvent

logger = get_logger(__name__)


class CallEventHandler:
    """
    Subscribes to AMI events and persists call lifecycle changes to PostgreSQL.
    
    Also writes to audit_logs for compliance purposes.
    """
    
    def __init__(self, ami: AsteriskAMI, session_factory) -> None:
        self._ami = ami
        self._session_factory = session_factory
        self._register_handlers()
    
    def _register_handlers(self) -> None:
        """Register all AMI event handlers."""
        self._ami.on_event("Dial", self._on_dial)
        self._ami.on_event("DialEnd", self._on_dial_end)
        self._ami.on_event("Hangup", self._on_hangup)
        self._ami.on_event("AgentConnect", self._on_agent_connect)
        self._ami.on_event("AgentComplete", self._on_agent_complete)
        self._ami.on_event("VarSet", self._on_varset)  # custom variables
    
    async def _on_dial(self, event: AMIEvent) -> None:
        """
        AMI Dial event — call is being dialed.
        Extract: Channel, DestChannel, CallerIDNum
        Update calls.status = 'initiated' if call_id in channel variables.
        """
        channel = event.headers.get("Channel", "")
        dest = event.headers.get("Destination", "")
        logger.info("AMI: Dial event", channel=channel, destination=dest)
        # Update DB: set status='initiated'
        await self._update_call_by_channel(channel, {"status": "initiated"})
    
    async def _on_dial_end(self, event: AMIEvent) -> None:
        """
        AMI DialEnd event — call was answered or not answered.
        DialStatus: ANSWER, NOANSWER, BUSY, CANCEL, CONGESTION
        """
        channel = event.headers.get("Channel", "")
        dial_status = event.headers.get("DialStatus", "")
        logger.info("AMI: DialEnd", channel=channel, status=dial_status)
        
        if dial_status == "ANSWER":
            await self._update_call_by_channel(channel, {
                "status": "answered",
                "answered_at": datetime.now(timezone.utc),
            })
        else:
            outcome_map = {
                "NOANSWER": "no_answer",
                "BUSY": "no_answer",
                "CANCEL": "no_answer",
                "CONGESTION": "failed",
            }
            await self._update_call_by_channel(channel, {
                "status": "completed",
                "outcome": outcome_map.get(dial_status, "failed"),
                "ended_at": datetime.now(timezone.utc),
            })
    
    async def _on_hangup(self, event: AMIEvent) -> None:
        """
        AMI Hangup event — channel has hung up.
        Compute duration if answered_at is set.
        """
        channel = event.headers.get("Channel", "")
        cause = event.headers.get("Cause", "0")
        cause_txt = event.headers.get("Cause-txt", "")
        logger.info("AMI: Hangup", channel=channel, cause=cause, cause_txt=cause_txt)
        
        async with self._session_factory() as session:
            result = await session.execute(
                select(Call).where(Call.asterisk_channel == channel)
            )
            call = result.scalar_one_or_none()
            if call:
                now = datetime.now(timezone.utc)
                call.ended_at = now
                if call.answered_at and call.status not in ("completed", "transferred"):
                    call.status = "completed"
                    duration = (now - call.answered_at).total_seconds()
                    call.duration_seconds = int(duration)
                
                # Audit log
                audit = AuditLog(
                    call_id=call.id,
                    lead_id=call.lead_id,
                    event_type="call_hangup",
                    payload={"cause": cause, "cause_txt": cause_txt, "channel": channel},
                )
                session.add(audit)
                await session.commit()
    
    async def _on_agent_connect(self, event: AMIEvent) -> None:
        """Agent picked up the transferred call."""
        logger.info("AMI: AgentConnect", headers=event.headers)
    
    async def _on_agent_complete(self, event: AMIEvent) -> None:
        """Agent call completed."""
        logger.info("AMI: AgentComplete", headers=event.headers)
    
    async def _on_varset(self, event: AMIEvent) -> None:
        """VarSet: custom variables set on channel (e.g. CALL_ID, LEAD_ID)."""
        variable = event.headers.get("Variable", "")
        value = event.headers.get("Value", "")
        if variable in ("CALL_ID", "LEAD_ID"):
            logger.debug("Channel variable set", variable=variable, value=value)
    
    async def _update_call_by_channel(
        self,
        channel: str,
        fields: dict,
    ) -> None:
        """Update call record matching asterisk_channel."""
        if not channel:
            return
        try:
            async with self._session_factory() as session:
                await session.execute(
                    update(Call)
                    .where(Call.asterisk_channel == channel)
                    .values(**fields)
                )
                await session.commit()
        except Exception as e:
            logger.exception("Failed to update call by channel", channel=channel, exc_info=e)
