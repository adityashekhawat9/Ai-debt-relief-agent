"""
AI Voice Platform — Application Settings

All configuration is loaded from environment variables (or .env file).
Fields without defaults are REQUIRED in production. In development, optional
fields have safe placeholder defaults so the app starts without all credentials.

Usage:
    from core.config import get_settings
    settings = get_settings()  # cached singleton via lru_cache
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Application ───────────────────────────────────────────────────────────
    APP_NAME: str = "AI Voice Platform"
    APP_ENV: str = "development"  # development | staging | production
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json | text

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://aicalls:changeme@localhost:5432/aicalls"
    POSTGRES_USER: str = "aicalls"
    POSTGRES_PASSWORD: str = "changeme"
    POSTGRES_DB: str = "aicalls"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 5
    DB_ECHO: bool = False

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 20

    # ── Qdrant ────────────────────────────────────────────────────────────────
    QDRANT_URL: str = "http://localhost:6333"

    # RAG Settings
    QDRANT_COLLECTION_NAME: str = "knowledge_base"
    QDRANT_VECTOR_SIZE: int = 384

    # ── AI Models ─────────────────────────────────────────────────────────────
    # NOTE: These paths are only required when the respective service starts.
    # The main API service will run without them set.
    USE_CLOUD_LLM: bool = True
    USE_CLOUD_STT: bool = True
    USE_CLOUD_TTS: bool = True
    ENABLE_CALL_RECORDING: bool = False
    GROQ_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    DEEPGRAM_API_KEY: str = ""
    CARTESIA_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""
    LLM_MODEL_PATH: str = "/models/qwen3-4b-q4_k_m.gguf"
    LLM_THREADS: int = 6
    LLM_N_CTX: int = 2048
    LLM_MAX_TOKENS: int = 150
    LLM_TEMPERATURE: float = 0.5
    LLM_N_GPU_LAYERS: int = 0  # CPU-only — never change this

    STT_MODEL: str = "small"
    STT_DEVICE: str = "cpu"
    STT_COMPUTE_TYPE: str = "int8"
    STT_CPU_THREADS: int = 4

    TTS_MODEL_PATH: str = "/models/piper/en_US-ryan-medium.onnx"
    PIPER_EXEC_PATH: str | None = None
    TTS_VOICE: str = "uYXf8XasLslADfZ2MB4u"

    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"

    # ── Asterisk / Vicidial ───────────────────────────────────────────────────
    DATA_WEBHOOK_URL: str = "https://olivialms.cloud/api/webhooks/ai-voice"
    VICIDIAL_BOT_API_URL: str = "http://103.113.27.27/bot_api/AmiHangup.php"
    VICIDIAL_BOT_API_KEY: str = "jbti89692vc60b2o9nu7647"
    TRANSFER_EXTENSION: str = "90009"

    # ── Business Rules (non-negotiable — match spec exactly) ──────────────────
    COMPANY_NAME: str = "YourCompanyName"
    MAX_CALL_DURATION_SECONDS: int = 300   # 5-minute hard limit
    CALL_TIMER_WARNING_SECONDS: int = 30   # Transition to POLITE_CLOSE at 4:30
    MAX_CALL_ATTEMPTS_PER_LEAD: int = 3
    MAX_CALL_ATTEMPTS_PERIOD_DAYS: int = 7
    MAX_OBJECTION_RETRIES: int = 2
    MAX_CONCURRENT_CALLS: int = 3          # Design for 2-3 simultaneous AI calls

    # ── Authentication ────────────────────────────────────────────────────────
    # IMPORTANT: Replace with `openssl rand -hex 32` in production
    JWT_SECRET_KEY: str = "dev-secret-key-replace-in-production-with-openssl-rand-hex-32"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480  # 8 hours

    ALLOWED_ORIGINS: str = "https://sakshamsagarfoundation.com"


    
    PUBLIC_APP_URL: str = ""  # The public URL (e.g. cloudflare tunnel) for Webhooks and WebSockets

    # ── Compliance APIs ───────────────────────────────────────────────────────
    # Set these before going live — stubs are used when empty
    FEDERAL_DNC_API_KEY: str = ""
    FEDERAL_DNC_API_URL: str = ""
    INDIA_DND_API_KEY: str = ""
    INDIA_DND_API_URL: str = ""

    # LiveKit
    LIVEKIT_URL: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    
    # Webhook
    OLIVIA_WEBHOOK_URL: str = ""

    # ── Monitoring ────────────────────────────────────────────────────────────
    PROMETHEUS_PORT: int = 9090
    GRAFANA_PORT: int = 3001
    LOKI_URL: str = "http://loki:3100"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings singleton. Call once; reuse everywhere."""
    return Settings()
