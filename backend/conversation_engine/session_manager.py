"""
Call Session Manager — Redis-backed per-call state management.

Key schema:
  call:{call_id}:session      → Hash  (all CallSession fields)
  call:{call_id}:transcript   → List  (JSON transcript entries, oldest first)
  call:{call_id}:writer_lock  → String (advisory lock for audio write coordination)
  dnc:{e164_phone}            → String "1" (DNC fast-lookup, no TTL)
  queue:llm                   → List  (LLM request queue, FIFO)
  queue:originate             → List  (outbound call originate queue)
  active:calls                → Set   (all currently active call_ids)
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

from core.logging import get_logger
from core.exceptions import RedisError

logger = get_logger(__name__)

# TTLs
CALL_SESSION_TTL = 3600   # 1 hour — auto-expire orphaned sessions
DNC_TTL = 0               # Never expire DNC entries (0 = no TTL in Redis)

# Key builders
def _session_key(call_id: str) -> str:
    return f"call:{call_id}:session"

def _transcript_key(call_id: str) -> str:
    return f"call:{call_id}:transcript"

def _dnc_key(phone: str) -> str:
    # Normalize: strip all non-digits, then prefix dnc:
    digits = ''.join(c for c in phone if c.isdigit())
    return f"dnc:{digits}"


@dataclass
class CallSession:
    call_id: str
    lead_id: str
    phone: str
    fsm_state: str = "WAIT_FOR_ANSWER"
    call_started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    answered_at: str | None = None
    qualification_answers: str = "{}"  # JSON string (Redis hash values are strings)
    objection_count: int = 0
    opt_out_detected: bool = False
    country: str = "US"  # 'US' | 'IN'
    channel_uuid: str = ""  # Asterisk AudioSocket channel UUID
    
    def get_qualification_answers(self) -> dict:
        try:
            return json.loads(self.qualification_answers)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_qualification_answers(self, answers: dict) -> None:
        self.qualification_answers = json.dumps(answers)


class SessionManager:
    """Redis-backed call session management with DNC cache and LLM queue."""
    
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client
    
    # ── Session CRUD ───────────────────────────────────────────────────────
    
    async def create_session(
        self,
        call_id: str,
        lead_id: str,
        phone: str,
        country: str = "US",
    ) -> CallSession:
        """
        Initialize a new call session in Redis.
        Creates the Hash with initial values and adds call_id to active:calls set.
        """
        session = CallSession(
            call_id=call_id,
            lead_id=lead_id,
            phone=phone,
            country=country,
        )
        
        # Store as Redis Hash (HSET with mapping)
        session_key = _session_key(call_id)
        data = asdict(session)
        # Convert booleans to strings for Redis compatibility
        data["opt_out_detected"] = str(data["opt_out_detected"]).lower()
        data["objection_count"] = str(data["objection_count"])
        
        pipe = self._redis.pipeline()
        pipe.hset(session_key, mapping=data)
        pipe.expire(session_key, CALL_SESSION_TTL)
        pipe.sadd("active:calls", call_id)
        await pipe.execute()
        
        logger.info("Session created", call_id=call_id, lead_id=lead_id)
        return session
    
    async def get_session(self, call_id: str) -> CallSession | None:
        """Retrieve call session from Redis. Returns None if not found."""
        data = await self._redis.hgetall(_session_key(call_id))
        if not data:
            return None
        
        return CallSession(
            call_id=data.get("call_id", call_id),
            lead_id=data.get("lead_id", ""),
            phone=data.get("phone", ""),
            fsm_state=data.get("fsm_state", "WAIT_FOR_ANSWER"),
            call_started_at=data.get("call_started_at", ""),
            answered_at=data.get("answered_at") or None,
            qualification_answers=data.get("qualification_answers", "{}"),
            objection_count=int(data.get("objection_count", 0)),
            opt_out_detected=data.get("opt_out_detected", "false").lower() == "true",
            country=data.get("country", "US"),
            channel_uuid=data.get("channel_uuid", ""),
        )
    
    async def update_session(self, call_id: str, **kwargs: Any) -> None:
        """
        Partial update of session fields.
        Example: await session_manager.update_session(call_id, fsm_state='QUALIFICATION')
        """
        if not kwargs:
            return
        
        # Serialize values for Redis
        data = {}
        for k, v in kwargs.items():
            if isinstance(v, bool):
                data[k] = str(v).lower()
            elif isinstance(v, dict):
                data[k] = json.dumps(v)
            elif v is None:
                data[k] = ""
            else:
                data[k] = str(v)
        
        session_key = _session_key(call_id)
        pipe = self._redis.pipeline()
        pipe.hset(session_key, mapping=data)
        pipe.expire(session_key, CALL_SESSION_TTL)  # Reset TTL on activity
        await pipe.execute()
        
        logger.debug("Session updated", call_id=call_id, fields=list(kwargs.keys()))
    
    async def delete_session(self, call_id: str) -> None:
        """Clean up session data when call ends."""
        pipe = self._redis.pipeline()
        pipe.delete(_session_key(call_id))
        pipe.delete(_transcript_key(call_id))
        pipe.srem("active:calls", call_id)
        await pipe.execute()
        logger.info("Session deleted", call_id=call_id)
    
    # ── Transcript management ──────────────────────────────────────────────
    
    async def append_transcript(
        self,
        call_id: str,
        speaker: str,      # 'ai' | 'lead'
        text: str,
        fsm_state: str,
        confidence: float = 1.0,
    ) -> None:
        """
        Append a transcript entry to Redis list.
        Each entry is a JSON string with speaker, text, fsm_state, timestamp.
        """
        entry = json.dumps({
            "speaker": speaker,
            "text": text,
            "fsm_state": fsm_state,
            "confidence": confidence,
            "spoken_at": datetime.now(timezone.utc).isoformat(),
        })
        transcript_key = _transcript_key(call_id)
        pipe = self._redis.pipeline()
        pipe.rpush(transcript_key, entry)
        pipe.expire(transcript_key, CALL_SESSION_TTL)
        await pipe.execute()
    
    async def get_transcript(self, call_id: str) -> list[dict]:
        """Get all transcript entries for a call."""
        raw_entries = await self._redis.lrange(_transcript_key(call_id), 0, -1)
        entries = []
        for raw in raw_entries:
            try:
                entries.append(json.loads(raw))
            except json.JSONDecodeError:
                logger.warning("Malformed transcript entry", call_id=call_id)
        return entries
    
    # ── DNC cache ──────────────────────────────────────────────────────────
    
    async def add_dnc(self, phone: str) -> None:
        """
        Add phone to DNC cache. MUST complete < 1 second (Redis SET is O(1)).
        Called immediately when opt-out is detected.
        No TTL — DNC entries live forever.
        """
        await self._redis.set(_dnc_key(phone), "1")
        logger.info("DNC added to Redis cache", phone=phone[:4] + "****")
    
    async def is_dnc(self, phone: str) -> bool:
        """Check if phone is in DNC cache. O(1) Redis GET."""
        result = await self._redis.get(_dnc_key(phone))
        return result is not None
    
    # ── Active call tracking ───────────────────────────────────────────────
    
    async def get_active_call_count(self) -> int:
        """Count currently active call sessions."""
        return await self._redis.scard("active:calls")
    
    async def get_active_call_ids(self) -> list[str]:
        """Return all active call IDs."""
        members = await self._redis.smembers("active:calls")
        return list(members)
    
    # ── LLM request queue ──────────────────────────────────────────────────
    
    async def enqueue_llm_request(self, request: dict) -> None:
        """
        Queue an LLM inference request.
        Used when 3 concurrent calls compete for the same CPU-only LLM.
        FIFO via Redis List RPUSH/BLPOP.
        """
        await self._redis.rpush("queue:llm", json.dumps(request))
        logger.debug("LLM request enqueued", call_id=request.get("call_id"))
    
    async def dequeue_llm_request(self, timeout: float = 0.0) -> dict | None:
        """
        Pop the next LLM request from the queue.
        timeout=0.0 means non-blocking (returns None immediately if empty).
        """
        if timeout > 0:
            result = await self._redis.blpop("queue:llm", timeout=int(timeout))
            if result:
                _, raw = result
                return json.loads(raw)
            return None
        else:
            raw = await self._redis.lpop("queue:llm")
            return json.loads(raw) if raw else None
    
    # ── Health check ───────────────────────────────────────────────────────
    
    async def health_check(self) -> bool:
        """Ping Redis and return True if healthy."""
        try:
            return await self._redis.ping()
        except Exception:
            return False
