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
