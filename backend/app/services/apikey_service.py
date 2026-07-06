"""API key persistence + verification."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key, hash_api_key
from app.db.models import ApiKey, User


async def create_key(db: AsyncSession, user: User, name: str) -> tuple[ApiKey, str]:
    """Create a key; returns (record, full_plaintext_key shown once)."""
    full_key, prefix, key_hash = generate_api_key()
    record = ApiKey(user_id=user.id, name=name, prefix=prefix, key_hash=key_hash)
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record, full_key


async def list_keys(db: AsyncSession, user: User) -> list[ApiKey]:
    res = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
    )
    return list(res.scalars().all())


async def revoke_key(db: AsyncSession, user: User, key_id: uuid.UUID) -> bool:
    res = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
    )
    key = res.scalar_one_or_none()
    if not key:
        return False
    key.revoked = True
    await db.flush()
    return True


async def resolve_user(db: AsyncSession, full_key: str) -> User | None:
    """Look up the owning, active user for a presented API key."""
    res = await db.execute(
        select(ApiKey).where(
            ApiKey.key_hash == hash_api_key(full_key), ApiKey.revoked.is_(False)
        )
    )
    key = res.scalar_one_or_none()
    if not key:
        return None
    key.last_used_at = datetime.now(timezone.utc)
    user = await db.get(User, key.user_id)
    if not user or not user.is_active:
        return None
    return user
