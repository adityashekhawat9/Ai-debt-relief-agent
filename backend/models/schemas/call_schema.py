from datetime import datetime
from uuid import UUID
from typing import Any

from pydantic import BaseModel, ConfigDict


class CallCreate(BaseModel):
    lead_id: UUID
    vicidial_call_id: str | None = None
    asterisk_channel: str | None = None
    direction: str = "outbound"
    status: str = "initiated"
    started_at: datetime | None = None


class CallUpdate(BaseModel):
    vicidial_call_id: str | None = None
    asterisk_channel: str | None = None
    status: str | None = None
    outcome: str | None = None
    answered_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    recording_path: str | None = None


class CallRead(BaseModel):
    id: UUID
    lead_id: UUID
    vicidial_call_id: str | None
    asterisk_channel: str | None
    direction: str
    status: str | None
    outcome: str | None
    started_at: datetime | None
    answered_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    recording_path: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TranscriptCreate(BaseModel):
    call_id: UUID
    speaker: str  # 'ai' | 'lead'
    text: str
    fsm_state: str | None = None
    confidence: float | None = None
    spoken_at: datetime


class TranscriptRead(BaseModel):
    id: UUID
    call_id: UUID
    speaker: str
    text: str
    fsm_state: str | None
    confidence: float | None
    spoken_at: datetime
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class QualificationAnswerRead(BaseModel):
    id: UUID
    call_id: UUID
    lead_id: UUID
    question_key: str
    question_text: str | None
    answer_text: str | None
    answer_bool: bool | None
    answered_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class AISummaryRead(BaseModel):
    id: UUID
    call_id: UUID
    summary_text: str
    summary_json: dict[str, Any] | None
    generated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AgentTransferRead(BaseModel):
    id: UUID
    call_id: UUID
    agent_id: str | None
    vicidial_agent_user: str | None
    transfer_initiated_at: datetime | None
    transfer_connected_at: datetime | None
    transfer_ended_at: datetime | None
    outcome: str | None
    model_config = ConfigDict(from_attributes=True)


class CallDetailResponse(BaseModel):
    """Full call detail including transcripts, qualification answers, and AI summary."""
    call: CallRead
    transcripts: list[TranscriptRead] = []
    qualification_answers: list[QualificationAnswerRead] = []
    ai_summary: AISummaryRead | None = None
    transfer: AgentTransferRead | None = None
    model_config = ConfigDict(from_attributes=True)
