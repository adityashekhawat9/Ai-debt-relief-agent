import os
import redis.asyncio as aioredis
from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)

# Fallback memory saver if redis is unavailable
from langgraph.checkpoint.memory import MemorySaver

class CheckpointerFactory:
    """
    Factory to retrieve the appropriate LangGraph checkpointer.
    Attempts to use Redis if configured, otherwise falls back to Memory.
    """
    _redis_pool = None

    @classmethod
    def get_checkpointer(cls):
        settings = get_settings()
        
        # LiveKit voice agents run in-memory for the duration of each call session.
        # MemorySaver provides 0ms latency checkpointing and avoids requiring
        # external RedisJSON modules (which cause "unknown command 'JSON.SET'" on standard Redis).
        return MemorySaver()

    @classmethod
    async def close(cls):
        if cls._redis_pool:
            await cls._redis_pool.aclose()
            cls._redis_pool = None
