"""API key management endpoints (per-user)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.schemas.auth import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from app.services import apikey_service

router = APIRouter(prefix="/keys", tags=["api-keys"])


@router.get("", response_model=list[ApiKeyOut])
async def list_keys(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list:
    return await apikey_service.list_keys(db, user)


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_key(
    body: ApiKeyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreated:
    record, full_key = await apikey_service.create_key(db, user, body.name)
    return ApiKeyCreated(
        id=record.id,
        name=record.name,
        prefix=record.prefix,
        revoked=record.revoked,
        last_used_at=record.last_used_at,
        created_at=record.created_at,
        key=full_key,
    )


@router.delete("/{key_id}")
async def revoke_key(
    key_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    ok = await apikey_service.revoke_key(db, user, key_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    return {"status": "revoked"}
