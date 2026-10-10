import os
import pathlib

base_path = r"c:\Users\RG0626\Desktop\Debt-relief-ai\ai-voice-platform\backend"

files = {
    "core/__init__.py": "",
    
    "core/config.py": """\
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App
    APP_NAME: str = "AI Voice Platform"
    APP_ENV: str = "development"  # development | staging | production
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json | text

    # Database
    DATABASE_URL: str  # postgresql+asyncpg://...
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 5
    DB_ECHO: bool = False

    # Redis
    REDIS_URL: str  # redis://redis:6379/0
    REDIS_MAX_CONNECTIONS: int = 20

    # Qdrant
    QDRANT_URL: str  # http://qdrant:6333
    QDRANT_COLLECTION_NAME: str = "knowledge_base"
    QDRANT_VECTOR_SIZE: int = 384

    # AI Models
    LLM_MODEL_PATH: str
    LLM_THREADS: int = 6
    LLM_N_CTX: int = 2048
    LLM_MAX_TOKENS: int = 150
    LLM_TEMPERATURE: float = 0.3
    LLM_N_GPU_LAYERS: int = 0
    STT_MODEL: str = "small"
    STT_DEVICE: str = "cpu"
    STT_COMPUTE_TYPE: str = "int8"
    STT_CPU_THREADS: int = 4
    TTS_MODEL_PATH: str
    TTS_VOICE: str = "en_US-ryan-medium"
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"

    # Asterisk
    ASTERISK_AMI_HOST: str = "asterisk"
    ASTERISK_AMI_PORT: int = 5038
    ASTERISK_AMI_USER: str
    ASTERISK_AMI_PASSWORD: str
    ASTERISK_ARI_URL: str
    ASTERISK_ARI_USER: str
    ASTERISK_ARI_PASSWORD: str
    AUDIOSOCKET_HOST: str = "0.0.0.0"
    AUDIOSOCKET_PORT: int = 9092

    # VICIdial
    LMS_BASE_URL: str

    # Business Rules
    COMPANY_NAME: str = "YourCompanyName"
    MAX_CALL_DURATION_SECONDS: int = 300
    CALL_TIMER_WARNING_SECONDS: int = 30
    MAX_CALL_ATTEMPTS_PER_LEAD: int = 3
    MAX_CALL_ATTEMPTS_PERIOD_DAYS: int = 7
    MAX_OBJECTION_RETRIES: int = 2
    MAX_CONCURRENT_CALLS: int = 3

    # Auth
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480

    # Compliance
    FEDERAL_DNC_API_KEY: str = ""
    FEDERAL_DNC_API_URL: str = ""
    INDIA_DND_API_KEY: str = ""
    INDIA_DND_API_URL: str = ""

    # Monitoring
    PROMETHEUS_PORT: int = 9090
    GRAFANA_PORT: int = 3001
    LOKI_URL: str = "http://loki:3100"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()
""",
    
    "core/logging.py": """\
import logging
import structlog
from core.config import Settings

def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)

def configure_logging(settings: Settings) -> None:
    if settings.LOG_FORMAT == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        renderer,
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(settings.LOG_LEVEL.upper())),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False
    )
""",

    "core/exceptions.py": """\
class AppException(Exception):
    \"\"\"Base exception for the application.\"\"\"
    def __init__(self, message: str, code: str, status_code: int = 500, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

class ComplianceError(AppException):
    \"\"\"Raised when a compliance check fails.\"\"\"
    def __init__(self, message: str, code: str = "COMPLIANCE_ERROR", status_code: int = 403, details: dict | None = None):
        super().__init__(message, code, status_code, details)

class DNCError(ComplianceError):
    \"\"\"Raised when lead is on Do Not Call list.\"\"\"
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="DNC_BLOCKED", details=details)

class CallingHoursError(ComplianceError):
    \"\"\"Raised when calling outside allowed hours.\"\"\"
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="OUTSIDE_CALLING_HOURS", details=details)

class ConsentMissingError(ComplianceError):
    \"\"\"Raised when lead consent is missing.\"\"\"
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="CONSENT_MISSING", details=details)

class CallTimerExpiredError(AppException):
    \"\"\"Raised when max call duration is reached.\"\"\"
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="CALL_TIMER_EXPIRED", status_code=408, details=details)

class TransferError(AppException):
    \"\"\"Raised when agent transfer fails.\"\"\"
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="TRANSFER_FAILED", status_code=502, details=details)

class AIServiceError(AppException):
    \"\"\"Base exception for AI service failures.\"\"\"
    def __init__(self, message: str, code: str = "AI_SERVICE_ERROR", status_code: int = 503, details: dict | None = None):
        super().__init__(message, code, status_code, details)

class STTError(AIServiceError):
    \"\"\"Raised when Speech-to-Text service fails.\"\"\"
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="STT_FAILED", details=details)

class LLMError(AIServiceError):
    \"\"\"Raised when Language Model service fails.\"\"\"
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="LLM_FAILED", details=details)

class TTSError(AIServiceError):
    \"\"\"Raised when Text-to-Speech service fails.\"\"\"
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="TTS_FAILED", details=details)

class DatabaseError(AppException):
    \"\"\"Raised when a database operation fails.\"\"\"
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="DB_ERROR", status_code=500, details=details)

class RedisError(AppException):
    \"\"\"Raised when a Redis operation fails.\"\"\"
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="REDIS_ERROR", status_code=500, details=details)

class NotFoundError(AppException):
    \"\"\"Raised when a requested resource is not found.\"\"\"
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="NOT_FOUND", status_code=404, details=details)

class ValidationError(AppException):
    \"\"\"Raised when data validation fails.\"\"\"
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="VALIDATION_ERROR", status_code=422, details=details)

class AuthenticationError(AppException):
    \"\"\"Raised when user authentication fails.\"\"\"
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="AUTH_FAILED", status_code=401, details=details)

class AuthorizationError(AppException):
    \"\"\"Raised when authenticated user lacks permissions.\"\"\"
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="FORBIDDEN", status_code=403, details=details)
""",

    "core/security.py": """\
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from core.exceptions import AuthenticationError, AuthorizationError

class UserRole(str, Enum):
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    AGENT = "agent"

class TokenData(BaseModel):
    sub: str  # user_id
    role: UserRole
    exp: datetime

class SecurityService:
    def __init__(self, secret_key: str, algorithm: str, expire_minutes: int):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.expire_minutes = expire_minutes
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(self, password: str) -> str:
        return self.pwd_context.hash(password)

    def verify_password(self, plain: str, hashed: str) -> bool:
        return self.pwd_context.verify(plain, hashed)

    def create_access_token(self, user_id: str, role: UserRole) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=self.expire_minutes)
        to_encode = {"sub": user_id, "role": role.value, "exp": expire}
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def decode_token(self, token: str) -> TokenData:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            sub: str = payload.get("sub")
            role: str = payload.get("role")
            exp = payload.get("exp")
            if sub is None or role is None or exp is None:
                raise AuthenticationError("Could not validate credentials")
            return TokenData(sub=sub, role=UserRole(role), exp=datetime.fromtimestamp(exp, tz=timezone.utc))
        except JWTError as e:
            raise AuthenticationError("Could not validate credentials") from e

    def require_role(self, token_data: TokenData, required_role: UserRole) -> None:
        role_hierarchy = {
            UserRole.ADMIN: 3,
            UserRole.SUPERVISOR: 2,
            UserRole.AGENT: 1,
        }
        user_level = role_hierarchy.get(token_data.role, 0)
        required_level = role_hierarchy.get(required_role, 99)
        
        if user_level < required_level:
            raise AuthorizationError("Insufficient permissions")
""",

    "database/__init__.py": "",

    "database/connection.py": """\
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import Settings

class Base(DeclarativeBase):
    pass

async def create_engine(settings: Settings) -> AsyncEngine:
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        echo=settings.DB_ECHO,
    )
    return engine

_engine: AsyncEngine | None = None

async def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        raise RuntimeError("Engine not initialized. Call init_db() first.")
    return _engine

async def init_db(settings: Settings) -> None:
    global _engine
    _engine = await create_engine(settings)

async def close_db() -> None:
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
""",

    "database/session.py": """\
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.connection import get_engine

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    engine = await get_engine()
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
""",

    "models/__init__.py": "",
    "models/database/__init__.py": "",

    "models/database/lead.py": """\
from datetime import datetime
from uuid import UUID
from sqlalchemy import String, Boolean, Integer, func, text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.connection import Base

class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
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
""",

    "models/database/call.py": """\
from datetime import datetime
from uuid import UUID
from sqlalchemy import String, Integer, ForeignKey, text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.connection import Base

class Call(Base):
    __tablename__ = "calls"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
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
    transcripts: Mapped[list["Transcript"]] = relationship("Transcript", back_populates="call")
""",

    "models/database/transcript.py": """\
from datetime import datetime
from uuid import UUID
from sqlalchemy import String, Text, Float, ForeignKey, text, TIMESTAMP
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
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))

    call: Mapped["Call"] = relationship("Call", back_populates="transcripts")
""",

    "models/database/qualification.py": """\
from datetime import datetime
from uuid import UUID
from sqlalchemy import String, ForeignKey, text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.connection import Base

class QualificationAnswer(Base):
    __tablename__ = "qualification_answers"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    call_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("calls.id"), nullable=False)
    question_key: Mapped[str] = mapped_column(String(100), nullable=False)
    answer_value: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))

class AISummary(Base):
    __tablename__ = "ai_summaries"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    call_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("calls.id"), nullable=False, unique=True)
    summary_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))

class AgentTransfer(Base):
    __tablename__ = "agent_transfers"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    call_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("calls.id"), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(100))
    transfer_status: Mapped[str] = mapped_column(String(50), nullable=False)
    transfer_reason: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))
""",

    "models/database/dnc.py": """\
from datetime import datetime
from uuid import UUID
from sqlalchemy import String, text, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from database.connection import Base

class InternalDNC(Base):
    __tablename__ = "internal_dnc"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    reason: Mapped[str | None] = mapped_column(String(200))
    added_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))

class DNCCheckLog(Base):
    __tablename__ = "dnc_check_log"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    check_source: Mapped[str] = mapped_column(String(50), nullable=False)
    is_blocked: Mapped[bool] = mapped_column(nullable=False)
    checked_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))

class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    lead_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    consent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    url_source: Mapped[str | None] = mapped_column(String(500))
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))
""",

    "models/database/audit.py": """\
from datetime import datetime
from uuid import UUID
from sqlalchemy import String, text, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.connection import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(100))
    call_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("calls.id"))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))

class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))
""",

    "models/schemas/__init__.py": "",

    "models/schemas/lead_schema.py": """\
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr

class LeadCreate(BaseModel):
    phone: str
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    state: str | None = None
    country: str = "US"
    timezone: str | None = None
    phone_type: Literal["mobile", "landline", "voip"] | None = None
    has_consent: bool = False
    source: str | None = None

class LeadUpdate(BaseModel):
    phone: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    state: str | None = None
    country: str | None = None
    timezone: str | None = None
    phone_type: Literal["mobile", "landline", "voip"] | None = None
    has_consent: bool | None = None
    call_attempts: int | None = None
    last_called_at: datetime | None = None
    dnc_flagged: bool | None = None
    status: str | None = None
    source: str | None = None

class LeadRead(BaseModel):
    id: UUID
    phone: str
    first_name: str | None
    last_name: str | None
    email: str | None
    state: str | None
    country: str
    timezone: str | None
    phone_type: str | None
    has_consent: bool
    call_attempts: int
    last_called_at: datetime | None
    dnc_flagged: bool
    status: str
    source: str | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class LeadListResponse(BaseModel):
    items: list[LeadRead]
    total: int
    page: int
    page_size: int
""",

    "models/schemas/call_schema.py": """\
from datetime import datetime
from uuid import UUID
from typing import Any
from pydantic import BaseModel, ConfigDict

class CallCreate(BaseModel):
    id: UUID
    lead_id: UUID
    vicidial_call_id: str | None = None
    asterisk_channel: str | None = None
    direction: str = "outbound"
    status: str | None = None
    outcome: str | None = None
    started_at: datetime | None = None
    answered_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    recording_path: str | None = None

class CallUpdate(BaseModel):
    vicidial_call_id: str | None = None
    asterisk_channel: str | None = None
    status: str | None = None
    outcome: str | None = None
    started_at: datetime | None = None
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
    id: UUID
    call_id: UUID | None = None
    speaker: str
    text: str
    fsm_state: str | None = None
    confidence: float | None = None
    spoken_at: datetime

class TranscriptRead(BaseModel):
    id: UUID
    call_id: UUID | None
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
    question_key: str
    answer_value: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class AISummaryRead(BaseModel):
    id: UUID
    call_id: UUID
    summary_json: dict[str, Any]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class AgentTransferRead(BaseModel):
    id: UUID
    call_id: UUID
    agent_id: str | None
    transfer_status: str
    transfer_reason: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class CallDetailResponse(BaseModel):
    call: CallRead
    transcripts: list[TranscriptRead]
    qualifications: list[QualificationAnswerRead]
    summary: AISummaryRead | None = None
""",

    "models/schemas/analytics_schema.py": """\
from datetime import date
from pydantic import BaseModel

class DailyCallStats(BaseModel):
    date: date
    total_calls: int
    answered_calls: int
    qualified_leads: int
    transfers: int
    opt_outs: int
    avg_duration_seconds: float
    call_abandonment_rate: float

class OutcomeBreakdown(BaseModel):
    outcome: str
    count: int
    percentage: float

class LatencyMetrics(BaseModel):
    vad_p50_ms: float
    vad_p95_ms: float
    stt_p50_ms: float
    stt_p95_ms: float
    llm_first_token_p50_ms: float
    llm_first_token_p95_ms: float
    tts_p50_ms: float
    tts_p95_ms: float
    end_to_end_p50_ms: float
    end_to_end_p95_ms: float

class DashboardSummary(BaseModel):
    active_calls: int
    calls_today: int
    qualified_today: int
    transfers_today: int
    dnc_blocks_today: int
    compliance_rate: float
    latency: LatencyMetrics
""",

    "database/migrations/alembic.ini": """\
[alembic]
script_location = database/migrations
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url =

[post_write_hooks]

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
""",

    "database/migrations/env.py": """\
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

from core.config import get_settings
from database.connection import Base
import models.database.lead
import models.database.call
import models.database.transcript
import models.database.qualification
import models.database.dnc
import models.database.audit

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()

def run_migrations_offline() -> None:
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.DATABASE_URL
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
""",

    "database/migrations/script.py.mako": """\
\"\"\"${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
\"\"\"
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}

def upgrade() -> None:
    ${upgrades if upgrades else "pass"}

def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
""",

    "database/migrations/versions/001_initial_schema.py": """\
\"\"\"initial schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2024-05-18 10:00:00.000000

\"\"\"
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # Leads
    op.create_table(
        'leads',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=True),
        sa.Column('last_name', sa.String(length=100), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('state', sa.String(length=2), nullable=True),
        sa.Column('country', sa.String(length=2), server_default='US', nullable=False),
        sa.Column('timezone', sa.String(length=50), nullable=True),
        sa.Column('phone_type', sa.String(length=20), nullable=True),
        sa.Column('has_consent', sa.Boolean(), server_default=sa.text('FALSE'), nullable=False),
        sa.Column('call_attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('last_called_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('dnc_flagged', sa.Boolean(), server_default=sa.text('FALSE'), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='new', nullable=False),
        sa.Column('source', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('phone')
    )
    op.create_index('idx_leads_phone', 'leads', ['phone'])
    op.create_index('idx_leads_status', 'leads', ['status'])

    # Calls
    op.create_table(
        'calls',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('lead_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('vicidial_call_id', sa.String(length=100), nullable=True),
        sa.Column('asterisk_channel', sa.String(length=200), nullable=True),
        sa.Column('direction', sa.String(length=20), server_default='outbound', nullable=False),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('outcome', sa.String(length=50), nullable=True),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('answered_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('ended_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('recording_path', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_calls_lead_id', 'calls', ['lead_id'])
    op.create_index('idx_calls_status', 'calls', ['status'])

    # Transcripts
    op.create_table(
        'transcripts',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('call_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('speaker', sa.String(length=10), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('fsm_state', sa.String(length=50), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('spoken_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_transcripts_call_id', 'transcripts', ['call_id'])

    # Qualification Answers
    op.create_table(
        'qualification_answers',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('call_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('question_key', sa.String(length=100), nullable=False),
        sa.Column('answer_value', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # AI Summaries
    op.create_table(
        'ai_summaries',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('call_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('summary_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('call_id')
    )

    # Agent Transfers
    op.create_table(
        'agent_transfers',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('call_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', sa.String(length=100), nullable=True),
        sa.Column('transfer_status', sa.String(length=50), nullable=False),
        sa.Column('transfer_reason', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Internal DNC
    op.create_table(
        'internal_dnc',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=True),
        sa.Column('added_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('phone')
    )
    op.create_index('idx_internal_dnc_phone', 'internal_dnc', ['phone'])

    # DNC Check Log
    op.create_table(
        'dnc_check_log',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('check_source', sa.String(length=50), nullable=False),
        sa.Column('is_blocked', sa.Boolean(), nullable=False),
        sa.Column('checked_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Consent Records
    op.create_table(
        'consent_records',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('lead_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('consent_type', sa.String(length=50), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('url_source', sa.String(length=500), nullable=True),
        sa.Column('timestamp', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Audit Logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('actor', sa.String(length=100), nullable=True),
        sa.Column('call_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_audit_logs_call_id', 'audit_logs', ['call_id'])

    # Knowledge Documents
    op.create_table(
        'knowledge_documents',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('content', sa.String(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade() -> None:
    op.drop_table('knowledge_documents')
    op.drop_table('audit_logs')
    op.drop_table('consent_records')
    op.drop_table('dnc_check_log')
    op.drop_table('internal_dnc')
    op.drop_table('agent_transfers')
    op.drop_table('ai_summaries')
    op.drop_table('qualification_answers')
    op.drop_table('transcripts')
    op.drop_table('calls')
    op.drop_table('leads')
"""
}

for rel_path, content in files.items():
    full_path = os.path.join(base_path, rel_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

print("Files generated.")
