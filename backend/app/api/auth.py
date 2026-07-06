"""Authentication endpoints: register, login, refresh, me."""

from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import (
    clear_auth_cookies,
    create_access_token,
    create_refresh_token,
    decode_token,
    set_auth_cookies,
)
from app.db.base import get_db
from app.db.models import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    UserOut,
)
from app.services import ratelimit, user_service

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _issue(response: Response, user: User) -> None:
    """Mint a fresh access/refresh pair and write them as httpOnly cookies."""
    set_auth_cookies(
        response,
        create_access_token(str(user.id), user.role),
        create_refresh_token(str(user.id)),
    )


def _client_ip(request: Request) -> str:
    """Best-effort client IP (behind nginx -> trust the left-most X-Forwarded-For)."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


async def _enforce_ip_rate(request: Request) -> None:
    redis = getattr(request.app.state, "redis", None)
    ok, retry = await ratelimit.check_ip_rate(
        redis, _client_ip(request), settings.auth_ip_rate_per_min, 60
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please wait and try again.",
            headers={"Retry-After": str(retry)},
        )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest, request: Request, response: Response,
    db: AsyncSession = Depends(get_db),
) -> User:
    await _enforce_ip_rate(request)
    if await user_service.get_by_email(db, body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    user = await user_service.create_user(db, body.email, body.password)
    _issue(response, user)
    return user


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginRequest, request: Request, response: Response,
    db: AsyncSession = Depends(get_db),
) -> User:
    await _enforce_ip_rate(request)
    redis = getattr(request.app.state, "redis", None)
    ident = body.email.strip().lower()

    locked, retry = await ratelimit.login_locked(redis, ident)
    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account temporarily locked after too many failed attempts.",
            headers={"Retry-After": str(retry)},
        )

    user = await user_service.authenticate(db, body.email, body.password)
    if user is None:
        await ratelimit.record_login_failure(
            redis, ident, settings.login_max_failures, settings.login_lockout_min * 60
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    await ratelimit.clear_login_failures(redis, ident)
    _issue(response, user)
    return user


@router.post("/refresh", response_model=UserOut)
async def refresh(
    request: Request, response: Response,
    body: RefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    # Web UI: refresh token comes from the httpOnly cookie. Legacy/SDK callers may
    # still pass it in the body.
    token = request.cookies.get(settings.refresh_cookie_name) or (
        body.refresh_token if body else None
    )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token"
        )
    try:
        payload = decode_token(token, expected_type="refresh")
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    user = await user_service.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    _issue(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response) -> dict[str, str]:
    clear_auth_cookies(response)
    return {"status": "logged out"}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
