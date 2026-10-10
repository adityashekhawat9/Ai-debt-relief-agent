from datetime import datetime
from uuid import UUID
from sqlalchemy import String, Text, Float, ForeignKey, text as sa_text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.connection import Base

class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    call_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("calls.id"))
    speaker: Mapped[str] = mapped_column(String(10), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    fsm_state: Mapped[str | None] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column(Float)
    spoken_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=sa_text("NOW()"))

    call: Mapped["Call"] = relationship("Call", back_populates="transcripts")
