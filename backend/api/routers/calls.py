from uuid import UUID
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, desc
from sqlalchemy.orm import selectinload

from api.dependencies import get_db, get_current_user, require_supervisor
from core.logging import get_logger
from core.exceptions import NotFoundError, DNCError, CallingHoursError
from models.database.call import Call
from models.database.lead import Lead
from conversation_engine.session_manager import SessionManager
from services.compliance.compliance_gate import ComplianceGate
from models.database.transcript import Transcript
from models.database.qualification import AISummary, QualificationAnswer
from models.database.audit import AuditLog
from models.schemas.call_schema import (
    CallRead, CallCreate, CallUpdate, CallDetailResponse,
    TranscriptRead, AISummaryRead, QualificationAnswerRead
)

router = APIRouter()
logger = get_logger(__name__)


@router.get("/health")
async def calls_health():
    return {"status": "ok", "service": "calls"}


@router.get("/", response_model=dict)
async def list_calls(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    outcome: str | None = Query(None),
    lead_id: UUID | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
):
    """
    List calls with pagination and optional filters.
    Returns {items: [...], total: N, page: N, page_size: N}
    """
    # Build base query
    stmt = select(Call).order_by(desc(Call.created_at))
    count_stmt = select(func.count(Call.id))
    
    # Apply filters
    if status:
        stmt = stmt.where(Call.status == status)
        count_stmt = count_stmt.where(Call.status == status)
    if outcome:
        stmt = stmt.where(Call.outcome == outcome)
        count_stmt = count_stmt.where(Call.outcome == outcome)
    if lead_id:
        stmt = stmt.where(Call.lead_id == lead_id)
        count_stmt = count_stmt.where(Call.lead_id == lead_id)
    if date_from:
        stmt = stmt.where(Call.created_at >= date_from)
        count_stmt = count_stmt.where(Call.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Call.created_at <= date_to)
        count_stmt = count_stmt.where(Call.created_at <= date_to)
    
    # Pagination
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    
    # Execute both queries
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()
    result = await db.execute(stmt)
    calls = result.scalars().all()
    
    logger.info("Listed calls", count=len(calls), total=total, page=page)
    return {
        "items": [CallRead.model_validate(c) for c in calls],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{call_id}", response_model=CallDetailResponse)
async def get_call_detail(
    call_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get complete call detail including transcripts, qualification answers, and AI summary.
    """
    result = await db.execute(
        select(Call)
        .where(Call.id == call_id)
        .options(
            selectinload(Call.transcripts),
            selectinload(Call.qualification_answers),
            selectinload(Call.ai_summaries),
        )
    )
    call = result.scalar_one_or_none()
    if not call:
        raise NotFoundError(f"Call {call_id} not found", code="NOT_FOUND")
    
    return CallDetailResponse.model_validate(call)


@router.post("/", response_model=CallRead, status_code=201)
async def create_call(
    payload: CallCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new call record. Called by telephony service when a call is initiated.
    """
    call = Call(**payload.model_dump())
    db.add(call)
    await db.flush()  # Get the UUID
    
    # Audit log
    audit = AuditLog(
        call_id=call.id,
        lead_id=call.lead_id,
        event_type="call_created",
        payload={"status": call.status, "direction": call.direction},
    )
    db.add(audit)
    await db.commit()
    await db.refresh(call)
    
    logger.info("Call created", call_id=str(call.id), lead_id=str(call.lead_id))
    return CallRead.model_validate(call)


@router.patch("/{call_id}", response_model=CallRead)
async def update_call(
    call_id: UUID,
    payload: CallUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update call status, outcome, recording path, etc.
    """
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise NotFoundError(f"Call {call_id} not found", code="NOT_FOUND")
    
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(call, field, value)
    
    await db.commit()
    await db.refresh(call)
    logger.info("Call updated", call_id=str(call_id), fields=list(update_data.keys()))
    return CallRead.model_validate(call)


@router.get("/{call_id}/transcripts", response_model=list[TranscriptRead])
async def list_transcripts(
    call_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    List all transcript entries for a call, in chronological order.
    """
    result = await db.execute(
        select(Transcript)
        .where(Transcript.call_id == call_id)
        .order_by(Transcript.spoken_at)
    )
    transcripts = result.scalars().all()
    return [TranscriptRead.model_validate(t) for t in transcripts]


@router.get("/{call_id}/summary", response_model=AISummaryRead | None)
async def get_call_summary(
    call_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get AI-generated summary for a call (produced before human transfer).
    Returns 404 if no summary exists.
    """
    result = await db.execute(
        select(AISummary).where(AISummary.call_id == call_id)
    )
    summary = result.scalar_one_or_none()
    if not summary:
        raise NotFoundError(f"No summary for call {call_id}", code="NOT_FOUND")
    return AISummaryRead.model_validate(summary)


@router.post("/{call_id}/end", dependencies=[Depends(require_supervisor)])
async def end_call(
    call_id: UUID,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Gracefully end an active call. Supervisor/admin only.
    Sends hangup via telephony service (Phase 2+).
    """
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise NotFoundError(f"Call {call_id} not found", code="NOT_FOUND")
    
    if call.status in ("completed", "failed", "transferred"):
        return {"status": "already_ended", "call_status": call.status}
    
    # Update status
    call.status = "completed"
    call.ended_at = datetime.utcnow()
    audit = AuditLog(
        call_id=call.id,
        lead_id=call.lead_id,
        event_type="call_ended_by_supervisor",
        payload={},
    )
    db.add(audit)
    await db.commit()
    
    logger.info("Call ended by supervisor", call_id=str(call_id))
    return {"status": "ended", "call_id": str(call_id)}


@router.post("/originate", status_code=202)
async def originate_call(
    lead_id: UUID,
    phone: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_supervisor),
):
    """
    Initiate an outbound call to a lead.
    Creates a call record and signals the telephony service via Redis.
    Phase 2: basic implementation. Full compliance gate in Phase 3.
    """
    from core.config import get_settings
    import redis.asyncio as aioredis
    import json
    
    settings = get_settings()
    
    # Fetch lead to get timezone and country for compliance checks
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    # Compliance checks
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    session_manager = SessionManager(redis_client)
    compliance_gate = ComplianceGate(session_manager)
    
    try:
        await compliance_gate.verify_can_call(
            phone=phone,
            country=lead.country,
            target_timezone=lead.timezone,
            db_session=db
        )
    except (DNCError, CallingHoursError) as e:
        await redis_client.aclose()
        raise HTTPException(status_code=403, detail=str(e))
        
    # Create call record
    call = Call(
        lead_id=lead_id,
        status="initiated",
        direction="outbound",
        started_at=datetime.utcnow(),
    )
    db.add(call)
    await db.flush()
    
    # Publish originate request to Redis queue
    await redis_client.rpush(
        "queue:originate",
        json.dumps({
            "call_id": str(call.id),
            "lead_id": str(lead_id),
            "phone": phone,
        }),
    )
    await redis_client.aclose()
    await db.commit()
    
    logger.info("Originate queued", call_id=str(call.id), phone=phone)
    return {"status": "queued", "call_id": str(call.id)}
