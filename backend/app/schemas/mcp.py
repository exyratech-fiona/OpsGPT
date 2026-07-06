"""Schemas for configurable MCP servers."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

_TYPE = r"^(kubernetes|elasticsearch|gitlab)$"


class McpTool(BaseModel):
    name: str
    description: str


class McpServerOut(BaseModel):
    id: uuid.UUID
    name: str
    provider_type: str
    display_name: str
    enabled: bool
    status: str
    status_message: str | None
    config: dict  # secrets masked
    tools: list[McpTool]
    created_at: datetime


class McpServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    provider_type: str = Field(pattern=_TYPE)
    config: dict = Field(default_factory=dict)
    enabled: bool = True


class McpServerUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    enabled: bool | None = None
    config: dict | None = None


class McpTestRequest(BaseModel):
    provider_type: str = Field(pattern=_TYPE)
    config: dict = Field(default_factory=dict)
    # if set, merge secrets from this saved server (so secrets needn't be re-entered)
    server_id: uuid.UUID | None = None


class McpTestResult(BaseModel):
    ok: bool
    message: str
