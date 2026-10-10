"""
AI Voice Platform — Async Database Session Factory

Provides:
- get_db()             : FastAPI dependency — yields an AsyncSession per request
- get_session_factory(): Returns the async_sessionmaker for direct use (e.g., health checks)
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.connection import get_engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Build and return a session factory bound to the current engine.

    Used directly when a session is needed outside the FastAPI DI system
    (e.g., the /health endpoint, background tasks, lifespan handlers).
    """
    import asyncio
    from database.connection import _engine  # noqa: PLC0415

    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call init_db() first.")

    return async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency — yields an AsyncSession for a single request.

    Usage:
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    engine = await get_engine()
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
