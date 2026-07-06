"""Shared FastAPI dependencies: authentication & authorization.

A request is authenticated by EITHER:
  - a JWT access token  (Authorization: Bearer <jwt>)         — used by the web UI
  - an API key          (Authorization: Bearer opsk_...)      — used by SDK/scripts
"""

from __future__ import annotations

import base64
import binascii
import uuid
from collections.abc import Awaitable, Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_token
from app.db.base import get_db
from app.db.models import User
from app.services import apikey_service, user_service

settings = get_settings()

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def _bearer_token(request: Request) -> str:
    # Web UI sends the access token as an httpOnly cookie; API-key/SDK clients send
    # it as an Authorization: Bearer header. Header wins when both are present.
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token:
        return token.strip()
    cookie = request.cookies.get(settings.access_cookie_name)
    if cookie:
        return cookie.strip()
    raise _UNAUTHORIZED


async def _basic_auth_user(request: Request, db: AsyncSession) -> User | None:
    """Authenticate via HTTP Basic (email:password) if that header is present.

    Lets clients that use a username/password (not an API key) call the API:
        Authorization: Basic base64(email:password)
    Credentials are sent on every request, so use only over TLS. bcrypt runs
    per request — for high-frequency callers an API key (opsk_) is cheaper.
    """
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "basic" or not value:
        return None
    try:
        decoded = base64.b64decode(value, validate=True).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise _UNAUTHORIZED
    email, sep, password = decoded.partition(":")
    if not sep:
        raise _UNAUTHORIZED
    user = await user_service.authenticate(db, email.strip(), password)
    if user is None:
        raise _UNAUTHORIZED
    return user


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    # username/password (HTTP Basic) path — for code that doesn't use API keys
    basic_user = await _basic_auth_user(request, db)
    if basic_user is not None:
        return basic_user

    token = _bearer_token(request)

    # API key path
    if token.startswith(settings.api_key_prefix):
        user = await apikey_service.resolve_user(db, token)
        if user is None:
            raise _UNAUTHORIZED
        return user

    # JWT path
    try:
        payload = decode_token(token, expected_type="access")
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _UNAUTHORIZED

    user = await user_service.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise _UNAUTHORIZED
    return user


def require_role(*roles: str) -> Callable[..., Awaitable[User]]:
    """Dependency factory: ensure the current user has one of `roles`."""

    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _checker
