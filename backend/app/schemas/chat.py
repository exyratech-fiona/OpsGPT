"""Request/response contracts for the chat API."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant"]


class Message(BaseModel):
    role: Role
    content: str = Field(min_length=1, max_length=100_000)


class ChatRequest(BaseModel):
    """Incoming chat request from the browser.

    `mode="auto"` lets OpsGPT pick the right specialist (chat/think/code/docs).
    Per-request generation overrides are optional; defaults come from settings.
    """

    messages: list[Message] = Field(min_length=1)
    mode: Literal[
        "auto", "ops-chat", "ops-think", "ops-code", "ops-docs", "ops-cluster"
    ] = "auto"
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)
    # ops-docs: restrict retrieval to these documents (None = all user's docs)
    document_ids: list[uuid.UUID] | None = None
    # MCP tool providers to enable for this turn (e.g. ["kubernetes"]).
    tool_providers: list[str] | None = None


class ModeInfo(BaseModel):
    id: str
    display_name: str
    model: str
    description: str
