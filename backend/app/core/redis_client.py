"""Async Redis client. Used for rate limiting and caching.

Redis is treated as optional infrastructure: if it's unavailable the app keeps
working (rate limiting fails open, caches are skipped).
"""

from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def create_redis() -> aioredis.Redis | None:
    try:
        client = aioredis.from_url(
            settings.redis_url,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        await client.ping()
        logger.info("redis_connected", extra={"url": settings.redis_url})
        return client
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        logger.error("redis_unavailable", extra={"error": str(exc)})
        return None
