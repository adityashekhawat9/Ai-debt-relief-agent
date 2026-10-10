"""
AI Voice Platform — FastAPI Application Entry Point

Handles lifespan startup/shutdown for all service connections:
- PostgreSQL (async SQLAlchemy)
- Redis (redis.asyncio connection pool)
- Qdrant (vector DB)

Exposes /health and /metrics globally, plus all API routers under /api/v1/.
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
from dotenv import load_dotenv
load_dotenv()

import time
import uuid
import asyncio
import subprocess
import sys
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import generate_latest

from core.config import get_settings
from core.exceptions import AppException
from core.logging import configure_logging, get_logger
from core.metrics import REQUEST_COUNT, REQUEST_DURATION
from database.connection import close_db, init_db
from services.rag.qdrant_client import QdrantService
from services.ai.llm_engine import CloudLLMEngine
from services.ai.rag_service import RAGService
from telephony.livekit_agent import start_livekit_worker

from api.routers import calls
# from api.routers import leads, agents, knowledge, analytics

logger = get_logger(__name__)

# Module-level singletons (set during lifespan startup)
_redis_pool: aioredis.Redis | None = None
_qdrant_service: QdrantService | None = None


def get_redis() -> aioredis.Redis:
    """Return the shared Redis connection pool."""
    if _redis_pool is None:
        raise RuntimeError("Redis not initialized. Check lifespan startup.")
    return _redis_pool


def get_qdrant() -> QdrantService:
    """Return the shared Qdrant service instance."""
    if _qdrant_service is None:
        raise RuntimeError("Qdrant not initialized. Check lifespan startup.")
    return _qdrant_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown for all service connections."""
    global _redis_pool, _qdrant_service
    
    # Telephony servers

    settings = get_settings()

    # 1. Configure structured logging
    configure_logging(settings)
    log = get_logger("lifespan")

    log.info("Bypassing DB, Redis, and Qdrant connections for WebSocket UI testing")

    log.info(
        "AI Voice Platform started",
        app_name=settings.APP_NAME,
        env=settings.APP_ENV,
        version="1.0.0",
    )

    # Boot Telephony layer
    try:
        # Initialize dependencies for the orchestrator
        llm_engine = CloudLLMEngine()
        # For testing we pass None for Qdrant unless initialized
        qdrant_service = RAGService()
        embedder_service = None

        # Telephony Orchestrator logic has moved entirely to livekit_agent.py
        
        # Start LiveKit Agent worker in a background subprocess
        env = os.environ.copy()
        livekit_process = subprocess.Popen(
            [sys.executable, "-m", "telephony.livekit_agent", "start"],
            env=env,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        log.info("Telephony server (LiveKit) booted in background.")
    except Exception as e:
        log.error(f"Failed to start telephony servers: {e}")
        livekit_process = None

    yield  # ← Application runs here

    # Shutdown
    log.info("Shutting down AI Voice Platform...")

    await close_db()
    log.info("PostgreSQL connections closed")

    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None
    log.info("Redis connections closed")

    if livekit_process:
        livekit_process.terminate()

    log.info("Shutdown complete")


# ── Application factory ────────────────────────────────────────────────────────

settings = get_settings()

app = FastAPI(
    title="AI Voice Platform",
    description="Production-grade AI outbound calling platform for debt relief",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


# ── Middleware ─────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",")] if settings.ALLOWED_ORIGINS else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_and_timing_middleware(request: Request, call_next):
    """Inject X-Request-ID header and log request timing. Bind context to structlog."""
    request_id = str(uuid.uuid4())
    start_time = time.perf_counter()

    # Bind request context to all log entries within this request
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    # Capture incoming request details
    client_ip = request.headers.get("X-Real-IP") or (request.client.host if request.client else "unknown")
    query_params = dict(request.query_params)

    try:
        response = await call_next(request)
    except Exception as e:
        logger.exception(f"Unhandled exception during request: {e}", path=request.url.path, client_ip=client_ip)
        raise

    duration_ms = (time.perf_counter() - start_time) * 1000
    response.headers["X-Request-ID"] = request_id

    # Prometheus metrics
    endpoint = request.url.path
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=endpoint,
        status=str(response.status_code),
    ).inc()
    REQUEST_DURATION.labels(
        method=request.method,
        endpoint=endpoint,
    ).observe(duration_ms / 1000.0)

    logger.info(
        "HTTP request",
        method=request.method,
        path=endpoint,
        client_ip=client_ip,
        query_params=query_params,
        status=response.status_code,
        duration_ms=round(duration_ms, 2),
        request_id=request_id,
    )

    return response


# ── Exception handlers ─────────────────────────────────────────────────────────

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle all application-level exceptions with structured error responses."""
    client_ip = request.headers.get("X-Real-IP") or (request.client.host if request.client else "unknown")
    logger.warning(
        "Application exception",
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        path=request.url.path,
        client_ip=client_ip,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors with field-level detail."""
    client_ip = request.headers.get("X-Real-IP") or (request.client.host if request.client else "unknown")
    logger.warning("Validation error on incoming request", path=request.url.path, client_ip=client_ip, errors=exc.errors())
    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler — logs full traceback and returns 500."""
    logger.exception(
        "Unhandled exception",
        path=request.url.path,
        method=request.method,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "details": None,
        },
    )


# ── Core routes ────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"], summary="Health check for all dependencies")
@app.get("/api/healthcheck", tags=["system"], include_in_schema=False)
@app.get("/api/health", tags=["system"], include_in_schema=False)
async def health_check() -> dict[str, Any]:
    """
    Check connectivity to PostgreSQL, Redis, and Qdrant.
    Returns 200 if all healthy, 503 if any dependency is degraded.
    """
    from sqlalchemy import text
    from database.session import get_session_factory

    services: dict[str, str] = {}
    overall_healthy = True

    # PostgreSQL check
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        services["postgres"] = "ok"
    except Exception as e:
        logger.error("PostgreSQL health check failed", error=str(e))
        services["postgres"] = "error"
        overall_healthy = False

    # Redis check
    try:
        redis = get_redis()
        await redis.ping()
        services["redis"] = "ok"
    except Exception as e:
        logger.error("Redis health check failed", error=str(e))
        services["redis"] = "error"
        overall_healthy = False

    # Qdrant check
    try:
        qdrant = get_qdrant()
        healthy = await qdrant.health_check()
        services["qdrant"] = "ok" if healthy else "error"
        if not healthy:
            overall_healthy = False
    except Exception as e:
        logger.error("Qdrant health check failed", error=str(e))
        services["qdrant"] = "error"
        overall_healthy = False

    status_code = 200 if overall_healthy else 503
    response_body = {
        "status": "ok" if overall_healthy else "degraded",
        "services": services,
        "version": "1.0.0",
    }

    return JSONResponse(content=response_body, status_code=status_code)


@app.get("/metrics", tags=["system"], summary="Prometheus metrics endpoint")
async def get_metrics() -> Response:
    """Prometheus exposition format. Restricted to Docker network via Nginx."""
    return Response(content=generate_latest(), media_type="text/plain; version=0.0.4")


# ── API Routers ────────────────────────────────────────────────────────────────

# app.include_router(leads.router, prefix="/api/v1/leads", tags=["Leads"])
app.include_router(calls.router, prefix="/api/v1/calls", tags=["Calls"])
# app.include_router(agents.router, prefix="/api/v1/agents", tags=["Agents"])
# app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["Knowledge Base"])
# app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["Analytics"])
try:
    from browser_test import router as browser_test_router
    app.include_router(browser_test_router.router, prefix="/api/v1/ws-test", tags=["ws-test"])
except ImportError as e:
    logger.warning(f"Could not load Browser Test router: {e}")



