"""Security primitives: password hashing, JWT, API-key generation.

No secrets are hard-coded — the JWT secret and TTLs come from settings.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Literal

import bcrypt
import jwt

from app.core.config import get_settings

if TYPE_CHECKING:
    from fastapi import Response

settings = get_settings()

TokenType = Literal["access", "refresh"]


# ---------- passwords ----------
def hash_password(password: str) -> str:
    # bcrypt has a 72-byte input limit; encode and let bcrypt handle salting.
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------- JWT ----------
def _create_token(sub: str, token_type: TokenType, ttl: timedelta, **extra: Any) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": sub,
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
        **extra,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, role: str) -> str:
    return _create_token(
        user_id,
        "access",
        timedelta(minutes=settings.access_token_ttl_min),
        role=role,
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        user_id, "refresh", timedelta(days=settings.refresh_token_ttl_days)
    )


def create_service_token(user_id: str, role: str, ttl_minutes: int) -> str:
    """Long-lived 'access' token for programmatic gateways that fetch once and
    cache the token (e.g. the GRC embedding provider). Accepted by get_current_user
    exactly like a normal access token."""
    return _create_token(user_id, "access", timedelta(minutes=ttl_minutes), role=role)


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Decode + validate a JWT. Raises jwt.PyJWTError on any problem."""
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected {expected_type} token")
    return payload


# ---------- API keys ----------
def generate_api_key() -> tuple[str, str, str]:
    """Return (full_key, prefix, key_hash).

    full_key is shown to the user exactly once. We persist only the hash.
    """
    raw = secrets.token_urlsafe(32)
    full_key = f"{settings.api_key_prefix}{raw}"
    prefix = full_key[: len(settings.api_key_prefix) + 6]
    return full_key, prefix, hash_api_key(full_key)


def hash_api_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode("utf-8")).hexdigest()


# ---------- auth cookies (web UI) ----------
def set_auth_cookies(response: "Response", access: str, refresh: str) -> None:
    """Write the access + refresh JWTs as httpOnly cookies (XSS-safe storage)."""
    common = {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "path": "/",
    }
    response.set_cookie(
        settings.access_cookie_name, access,
        max_age=settings.access_token_ttl_min * 60, **common,
    )
    response.set_cookie(
        settings.refresh_cookie_name, refresh,
        max_age=settings.refresh_token_ttl_days * 86400, **common,
    )


def clear_auth_cookies(response: "Response") -> None:
    for name in (settings.access_cookie_name, settings.refresh_cookie_name):
        response.delete_cookie(
            name, path="/", httponly=True,
            secure=settings.cookie_secure, samesite=settings.cookie_samesite,
        )
