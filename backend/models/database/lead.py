from datetime import datetime
from uuid import UUID
from sqlalchemy import String, Boolean, Integer, func, text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.connection import Base

class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    vicidial_lead_id: Mapped[str | None] = mapped_column(String(50))
    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[str | None] = mapped_column(String(2))
    country: Mapped[str] = mapped_column(String(2), nullable=False, server_default="US")
    timezone: Mapped[str | None] = mapped_column(String(50))
    phone_type: Mapped[str | None] = mapped_column(String(20))
    has_consent: Mapped[bool] = mapped_column(Boolean, server_default=text("FALSE"))
    call_attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_called_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    dnc_flagged: Mapped[bool] = mapped_column(Boolean, server_default=text("FALSE"))
    status: Mapped[str] = mapped_column(String(50), server_default="new")
    source: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"), onupdate=func.now())

    calls: Mapped[list["Call"]] = relationship("Call", back_populates="lead")

    def __repr__(self) -> str:
        return f"<Lead(id={self.id}, phone={self.phone}, status={self.status})>"
