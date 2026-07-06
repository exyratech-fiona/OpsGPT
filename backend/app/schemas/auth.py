"""Auth & user request/response schemas."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

# Permissive email validation: accepts internal/self-hosted domains (e.g.
# user@company.local, admin@corp) that strict deliverability checks reject,
# while still requiring a sane local@domain shape. Normalised to lowercase.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError("email must be a string")
    v = v.strip().lower()
    if not _EMAIL_RE.match(v):
        raise ValueError("invalid email address")
    return v


Email = Annotated[str, BeforeValidator(_normalize_email)]


class RegisterRequest(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    is_active: bool
    daily_token_limit: int = 0
    tokens_used_today: int = 0
    tokens_used_total: int = 0
    usage_date: date | None = None
    created_at: datetime


# ---- API keys ----
class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    prefix: str
    revoked: bool
    last_used_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyOut):
    # Returned ONLY at creation time; the full key is never retrievable again.
    key: str


# ---- admin ----
class RoleUpdate(BaseModel):
    role: str = Field(pattern="^(admin|user|guest)$")


class ActiveUpdate(BaseModel):
    is_active: bool


class LimitUpdate(BaseModel):
    # 0 = unlimited
    daily_token_limit: int = Field(ge=0, le=100_000_000)


class AdminCreateUser(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="user", pattern="^(admin|user|guest)$")
    daily_token_limit: int = Field(default=0, ge=0, le=100_000_000)
