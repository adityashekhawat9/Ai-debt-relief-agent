"""
SQLAlchemy ORM models for qualification and transfer tracking tables.

Tables:
  qualification_answers  — Q&A pairs for each call
  ai_summaries           — Pre-transfer LLM-generated summaries
  agent_transfers        — Human transfer lifecycle
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text, text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from typing import TYPE_CHECKING
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from models.database.call import Call
    from models.database.lead import Lead

from database.connection import Base


class QualificationAnswer(Base):
    """Stores each qualification question-answer pair for a call."""

    __tablename__ = "qualification_answers"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    call_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("calls.id"), nullable=False
    )
    lead_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("leads.id"), nullable=False
    )
    question_key: Mapped[str] = mapped_column(String(100), nullable=False)
    question_text: Mapped[str | None] = mapped_column(Text)
    answer_text: Mapped[str | None] = mapped_column(Text)
    answer_bool: Mapped[bool | None] = mapped_column(Boolean)
    answered_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("NOW()")
    )

    # Relationships
    call: Mapped["Call"] = relationship("Call", back_populates="qualification_answers")
    lead: Mapped["Lead"] = relationship("Lead")

    def __repr__(self) -> str:
        return f"<QualificationAnswer call={self.call_id} key={self.question_key!r}>"


class AISummary(Base):
    """AI-generated structured summary produced before human transfer."""

    __tablename__ = "ai_summaries"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    call_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("calls.id"), nullable=False
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    summary_json: Mapped[dict | None] = mapped_column(JSONB)
    generated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("NOW()")
    )

    # Relationships
    call: Mapped["Call"] = relationship("Call", back_populates="ai_summaries")

    def __repr__(self) -> str:
        return f"<AISummary call={self.call_id}>"


class AgentTransfer(Base):
    """Records the full lifecycle of a human agent transfer."""

    __tablename__ = "agent_transfers"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    call_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("calls.id"), nullable=False
    )
    agent_id: Mapped[str | None] = mapped_column(String(100))
    vicidial_agent_user: Mapped[str | None] = mapped_column(String(100))
    transfer_initiated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    transfer_connected_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    transfer_ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(50))

    # Relationships
    call: Mapped["Call"] = relationship("Call", back_populates="agent_transfers")

    def __repr__(self) -> str:
        return f"<AgentTransfer call={self.call_id} agent={self.agent_id!r}>"
