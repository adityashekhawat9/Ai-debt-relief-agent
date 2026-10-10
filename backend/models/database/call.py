from datetime import datetime
from uuid import UUID
from sqlalchemy import String, Integer, ForeignKey, text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from typing import TYPE_CHECKING
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from models.database.lead import Lead
    from models.database.transcript import Transcript
    from models.database.qualification import QualificationAnswer, AISummary, AgentTransfer

from database.connection import Base

class Call(Base):
    __tablename__ = "calls"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    lead_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    vicidial_call_id: Mapped[str | None] = mapped_column(String(100))
    asterisk_channel: Mapped[str | None] = mapped_column(String(200))
    direction: Mapped[str] = mapped_column(String(20), server_default="outbound")
    status: Mapped[str | None] = mapped_column(String(50))
    outcome: Mapped[str | None] = mapped_column(String(50))
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    recording_path: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))

    lead: Mapped["Lead"] = relationship("Lead", back_populates="calls")
    transcripts: Mapped[list["Transcript"]] = relationship(
        "Transcript", back_populates="call", cascade="all, delete-orphan"
    )
    qualification_answers: Mapped[list["QualificationAnswer"]] = relationship(
        "QualificationAnswer", back_populates="call", cascade="all, delete-orphan"
    )
    ai_summaries: Mapped[list["AISummary"]] = relationship(
        "AISummary", back_populates="call", cascade="all, delete-orphan"
    )
    agent_transfers: Mapped[list["AgentTransfer"]] = relationship(
        "AgentTransfer", back_populates="call", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Call id={self.id} lead={self.lead_id} status={self.status!r}>"
