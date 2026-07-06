"""User persistence + authentication logic."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.db.base import AsyncSessionLocal
from app.db.models import Role, User


def _today():
    return datetime.now(timezone.utc).date()


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    res = await db.execute(select(User).where(User.email == email.lower()))
    return res.scalar_one_or_none()


async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def count_users(db: AsyncSession) -> int:
    res = await db.execute(select(func.count()).select_from(User))
    return int(res.scalar_one())


async def create_user(
    db: AsyncSession, email: str, password: str, role: str = Role.user.value
) -> User:
    user = User(
        email=email.lower(),
        hashed_password=hash_password(password),
        role=role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_by_email(db, email)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def is_over_quota(user: User) -> bool:
    """True if the user has hit today's token limit (0 limit = unlimited)."""
    if not user.daily_token_limit or user.daily_token_limit <= 0:
        return False
    if user.usage_date != _today():
        return False  # counter is for a previous day -> effectively reset
    return user.tokens_used_today >= user.daily_token_limit


async def record_usage(user_id: uuid.UUID, tokens: int) -> None:
    """Add generated tokens to a user's daily + lifetime usage (own session)."""
    if tokens <= 0:
        return
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None:
            return
        today = _today()
        if user.usage_date != today:
            user.usage_date = today
            user.tokens_used_today = 0
        user.tokens_used_today += tokens
        user.tokens_used_total = (user.tokens_used_total or 0) + tokens
        await session.commit()
