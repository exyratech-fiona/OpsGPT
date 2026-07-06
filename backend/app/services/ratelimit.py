"""Per-user fixed-window rate limiting backed by Redis (fails open)."""

from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)


async def check_and_increment(
    redis, user_id: str, limit: int, window_s: int = 60
) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds).

    Fixed window: one counter per user that expires after `window_s`. If Redis is
    down or limit<=0, always allow (fail open) so chat never breaks on infra.
    """
    if redis is None or limit <= 0:
        return True, 0
    key = f"rl:{user_id}"
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_s)
        if count > limit:
            ttl = await redis.ttl(key)
            return False, max(int(ttl), 1)
        return True, 0
    except Exception as exc:  # noqa: BLE001
        logger.error("ratelimit_error", extra={"error": str(exc)})
        return True, 0


async def check_ip_rate(redis, ip: str, limit: int, window_s: int = 60) -> tuple[bool, int]:
    """Per-client-IP fixed-window limiter (for unauthenticated auth endpoints)."""
    if redis is None or limit <= 0 or not ip:
        return True, 0
    key = f"rlip:{ip}"
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_s)
        if count > limit:
            ttl = await redis.ttl(key)
            return False, max(int(ttl), 1)
        return True, 0
    except Exception as exc:  # noqa: BLE001
        logger.error("ip_ratelimit_error", extra={"error": str(exc)})
        return True, 0


async def login_locked(redis, ident: str) -> tuple[bool, int]:
    """Return (locked, retry_after_seconds) for an identity (email) under lockout."""
    if redis is None or not ident:
        return False, 0
    try:
        if await redis.get(f"lock:{ident}") is not None:
            ttl = await redis.ttl(f"lock:{ident}")
            return True, max(int(ttl), 1)
    except Exception as exc:  # noqa: BLE001
        logger.error("login_lock_check_error", extra={"error": str(exc)})
    return False, 0


async def record_login_failure(redis, ident: str, max_failures: int, lockout_s: int) -> None:
    """Count a failed login; trip a lockout once max_failures is reached."""
    if redis is None or not ident:
        return
    try:
        key = f"fail:{ident}"
        n = await redis.incr(key)
        if n == 1:
            await redis.expire(key, lockout_s)
        if n >= max_failures:
            await redis.set(f"lock:{ident}", "1", ex=lockout_s)
    except Exception as exc:  # noqa: BLE001
        logger.error("login_fail_record_error", extra={"error": str(exc)})


async def clear_login_failures(redis, ident: str) -> None:
    """Reset the failure counter + lockout after a successful login."""
    if redis is None or not ident:
        return
    try:
        await redis.delete(f"fail:{ident}", f"lock:{ident}")
    except Exception as exc:  # noqa: BLE001
        logger.debug("login_fail_clear_error", extra={"error": str(exc)})
