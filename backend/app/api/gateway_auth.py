"""Token endpoint for programmatic gateway clients (e.g. the GRC platform's
remote embedding provider) that authenticate with a username+password and expect
a bearer token in the response, then cache it.

    POST /auth/token   (also POST /v1/token)

Accepts the credentials in whatever shape the client sends:
  * JSON:            {"username"|"email"|"user": ..., "password"|"pass": ...}
  * form-urlencoded: username=...&password=...  (incl. OAuth2 grant_type=password)
  * HTTP Basic:      Authorization: Basic base64(user:pass)

Returns the token under several field aliases so different client libraries all
find it. The token is a long-lived access JWT (get_current_user accepts it).
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable
from urllib.parse import parse_qs

import orjson
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import create_service_token
from app.db.base import get_db
from app.services import user_service

logger = get_logger(__name__)
router = APIRouter(tags=["gateway-auth"])


def _pick(get: Callable[[str], str | None]) -> tuple[str | None, str | None]:
    user = get("username") or get("email") or get("user") or get("client_id")
    pw = get("password") or get("pass") or get("passwd") or get("client_secret")
    return user, pw


async def _extract(request: Request) -> tuple[str | None, str | None]:
    raw = await request.body()
    ctype = request.headers.get("content-type", "").lower()

    # JSON body
    if raw and ("json" in ctype or raw.lstrip()[:1] in (b"{", b"[")):
        try:
            data = orjson.loads(raw)
            if isinstance(data, dict):
                u, p = _pick(lambda k: _as_str(data.get(k)))
                if u and p:
                    return u, p
        except orjson.JSONDecodeError:
            pass

    # form-urlencoded / OAuth2 password grant
    if raw and b"=" in raw:
        form = parse_qs(raw.decode("utf-8", "ignore"))
        u, p = _pick(lambda k: (form.get(k) or [None])[0])
        if u and p:
            return u, p

    # HTTP Basic
    auth = request.headers.get("Authorization", "")
    scheme, _, val = auth.partition(" ")
    if scheme.lower() == "basic" and val:
        try:
            dec = base64.b64decode(val, validate=True).decode("utf-8")
            u, _, p = dec.partition(":")
            if u and p:
                return u, p
        except (binascii.Error, ValueError, UnicodeDecodeError):
            pass

    return None, None


def _as_str(v: object) -> str | None:
    return v if isinstance(v, str) else None


async def _issue(request: Request, db: AsyncSession) -> dict:
    username, password = await _extract(request)
    if not username or not password:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Provide username/email and password (JSON, form, or Basic).",
        )
    user = await user_service.authenticate(db, username.strip(), password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    settings = get_settings()
    ttl_min = settings.token_endpoint_ttl_min
    token = create_service_token(str(user.id), user.role, ttl_min)
    expires_in = ttl_min * 60
    logger.info("gateway_token_issued", extra={"user_role": user.role})
    return {
        "access_token": token,
        "token": token,
        "accessToken": token,
        "token_type": "Bearer",
        "tokenType": "Bearer",
        "expires_in": expires_in,
        "expiresIn": expires_in,
        "scope": "api",
    }


@router.post("/auth/token", summary="Get a bearer token from username+password")
async def auth_token(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    return await _issue(request, db)


@router.post("/v1/token", summary="Get a bearer token (alias of /auth/token)")
async def v1_token(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    return await _issue(request, db)
