"""Admin-only endpoints: user administration."""

from __future__ import annotations

import uuid

import psutil
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.metrics import RUNTIME
from app.db.base import get_db
from app.db.models import Document, Role, User
from app.schemas.auth import (
    ActiveUpdate,
    AdminCreateUser,
    LimitUpdate,
    RoleUpdate,
    UserOut,
)
from app.services import user_service

router = APIRouter(prefix="/admin", tags=["admin"])

# every route here requires an admin
admin_only = require_role(Role.admin.value)


@router.get("/stats")
async def stats(
    request: Request,
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Aggregate stats for the in-app admin dashboard."""
    users_total = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    docs_total = (await db.execute(select(func.count()).select_from(Document))).scalar_one()

    clients = request.app.state.llama_clients
    models = {name: await c.health() for name, c in clients.items()}
    embed_ok = await request.app.state.embed.health()

    vm = psutil.virtual_memory()
    try:
        load = list(psutil.getloadavg())
    except (AttributeError, OSError):
        load = [0.0, 0.0, 0.0]
    system = {
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "cpu_count": psutil.cpu_count(),
        "mem_total": vm.total,
        "mem_used": vm.used,
        "mem_percent": vm.percent,
        "load_avg": load,
    }
    return {
        "users": int(users_total),
        "documents": int(docs_total),
        "chats": int(RUNTIME["chats"]),
        "tokens": int(RUNTIME["tokens"]),
        "tool_calls": int(RUNTIME["tool_calls"]),
        "models": models,
        "embed": embed_ok,
        "system": system,
    }


@router.get("/users", response_model=list[UserOut])
async def list_users(
    _: User = Depends(admin_only), db: AsyncSession = Depends(get_db)
) -> list:
    res = await db.execute(select(User).order_by(User.created_at.desc()))
    return list(res.scalars().all())


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: AdminCreateUser,
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Admin creates a user directly with a chosen role + optional token limit."""
    if await user_service.get_by_email(db, body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    user = await user_service.create_user(db, body.email, body.password, role=body.role)
    user.daily_token_limit = body.daily_token_limit
    await db.flush()
    await db.refresh(user)
    return user


@router.patch("/users/{user_id}/role", response_model=UserOut)
async def set_role(
    user_id: uuid.UUID,
    body: RoleUpdate,
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.role = body.role
    await db.flush()
    return user


@router.patch("/users/{user_id}/active", response_model=UserOut)
async def set_active(
    user_id: uuid.UUID,
    body: ActiveUpdate,
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.is_active = body.is_active
    await db.flush()
    return user


@router.patch("/users/{user_id}/limit", response_model=UserOut)
async def set_limit(
    user_id: uuid.UUID,
    body: LimitUpdate,
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Set a user's daily token limit (0 = unlimited)."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.daily_token_limit = body.daily_token_limit
    await db.flush()
    return user
