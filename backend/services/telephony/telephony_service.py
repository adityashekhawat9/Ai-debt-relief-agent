"""
Telephony Service — FastAPI microservice for call lifecycle management.

Runs:
- AudioSocket TCP server (port 9092) — receives audio from Asterisk
- AMI client — connects to Asterisk for call control events
- ARI client — WebSocket event stream from Asterisk
- Call registry — tracks active CallOrchestrator instances

Exposes:
- GET  /health  — service health + Asterisk connectivity
- GET  /metrics — Prometheus metrics
- GET  /calls/active — list active call sessions
- POST /calls/originate — initiate outbound call (called by main API)
- POST /calls/{channel_uuid}/hangup — force hang up
- POST /ami/event — AMI event webhook (internal)
"""

from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from prometheus_client import generate_latest

from core.config import get_settings
from core.logging import configure_logging, get_logger
from core.metrics import ACTIVE_CALLS
from services.telephony.asterisk_ami import AsteriskAMI
from services.telephony.asterisk_ari import AsteriskARI
from services.telephony.audiosocket import AudioSocketServer, AudioSocketSession
from conversation_engine.call_orchestrator import CallOrchestrator
from conversation_engine.session_manager import SessionManager

logger = get_logger(__name__)

# Global service singletons
_ami: AsteriskAMI | None = None
_ari: AsteriskARI | None = None
_audiosocket: AudioSocketServer | None = None
_session_manager: SessionManager | None = None

# Active calls registry: channel_uuid → CallOrchestrator
_active_calls: dict[str, CallOrchestrator] = {}


async def on_audiosocket_session_start(session: AudioSocketSession) -> None:
    """
    Called when Asterisk connects a new AudioSocket session.
    
    1. Look up the call_id by channel_uuid in Redis
    2. Create a CallOrchestrator for this call
    3. Register in _active_calls
    4. Start the orchestrator
    """
    logger.info(
        "AudioSocket session started",
        channel_uuid=session.channel_uuid,
        remote_addr=session.remote_addr,
    )
    # Phase 2 POC: just run echo
    await _audiosocket.echo_session(session)


async def on_audiosocket_session_end(session: AudioSocketSession) -> None:
    """Called when Asterisk disconnects an AudioSocket session."""
    logger.info(
        "AudioSocket session ended",
        channel_uuid=session.channel_uuid,
        bytes_received=session.bytes_received,
        bytes_sent=session.bytes_sent,
    )
    orchestrator = _active_calls.pop(session.channel_uuid, None)
    if orchestrator and orchestrator.is_active:
        await orchestrator.end_call(reason="audiosocket_disconnect")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ami, _ari, _audiosocket, _session_manager
    settings = get_settings()
    configure_logging(settings)
    log = get_logger("telephony.lifespan")
    
    # Redis for session management
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    _session_manager = SessionManager(redis_client)
    
    # AudioSocket TCP server
    _audiosocket = AudioSocketServer(
        host=settings.AUDIOSOCKET_HOST,
        port=settings.AUDIOSOCKET_PORT,
    )
    _audiosocket.on_session_start(on_audiosocket_session_start)
    _audiosocket.on_session_end(on_audiosocket_session_end)
    await _audiosocket.start()
    log.info("AudioSocket server started", port=settings.AUDIOSOCKET_PORT)
    
    # AMI connection
    _ami = AsteriskAMI(
        host=settings.ASTERISK_AMI_HOST,
        port=settings.ASTERISK_AMI_PORT,
        username=settings.ASTERISK_AMI_USER,
        password=settings.ASTERISK_AMI_PASSWORD,
    )
    try:
        await _ami.connect()
        log.info("AMI connected", host=settings.ASTERISK_AMI_HOST)
    except Exception as e:
        log.warning("AMI connection failed (Asterisk not ready)", error=str(e))
    
    # ARI connection
    _ari = AsteriskARI(
        base_url=settings.ASTERISK_ARI_URL,
        username=settings.ASTERISK_ARI_USER,
        password=settings.ASTERISK_ARI_PASSWORD,
    )
    try:
        await _ari.connect()
        log.info("ARI connected", url=settings.ASTERISK_ARI_URL)
    except Exception as e:
        log.warning("ARI connection failed (Asterisk not ready)", error=str(e))
    
    log.info("Telephony service ready")
    yield
    
    # Shutdown
    if _ami:
        await _ami.disconnect()
    if _ari:
        await _ari.disconnect()
    if _audiosocket:
        await _audiosocket.stop()
    await redis_client.aclose()
    log.info("Telephony service shutdown complete")


app = FastAPI(
    title="AI Voice Platform — Telephony Service",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> JSONResponse:
    services: dict[str, Any] = {}
    
    # AudioSocket
    services["audiosocket"] = {
        "status": "ok" if _audiosocket else "error",
        "active_sessions": _audiosocket.get_active_session_count() if _audiosocket else 0,
    }
    
    # AMI
    services["ami"] = {
        "status": "ok" if (_ami and _ami.is_connected) else "degraded",
    }
    
    # ARI
    try:
        ari_ok = await _ari.health_check() if _ari else False
        services["ari"] = {"status": "ok" if ari_ok else "degraded"}
    except Exception:
        services["ari"] = {"status": "error"}
    
    overall = all(s.get("status") == "ok" for s in services.values())
    return JSONResponse(
        status_code=200 if overall else 206,
        content={"status": "ok" if overall else "degraded", "services": services},
    )


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type="text/plain; version=0.0.4")


@app.get("/calls/active")
async def list_active_calls() -> dict:
    return {
        "count": len(_active_calls),
        "calls": [
            {
                "call_id": orch.call_id,
                "channel_uuid": channel_uuid,
                "duration_seconds": orch.duration_seconds,
            }
            for channel_uuid, orch in _active_calls.items()
        ],
    }
