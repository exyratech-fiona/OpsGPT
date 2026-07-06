"""Async client for the upstream llama.cpp OpenAI-compatible server.

Owns a single pooled httpx client for the process lifetime. Exposes a streaming
chat method that yields plain text deltas, hiding the SSE wire format of the
upstream from the rest of the app.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Literal

import httpx
import orjson

from app.core.logging import get_logger

logger = get_logger(__name__)


class LlamaClientError(RuntimeError):
    """Raised when the upstream inference server fails."""


def _stats_from_timings(timings: dict) -> dict:
    """Map llama.cpp timing fields to a compact {tokens, tps} stat."""
    n = int(timings.get("predicted_n", 0) or 0)
    ms = float(timings.get("predicted_ms", 0) or 0)
    tps = round(n / (ms / 1000.0), 2) if ms > 0 else 0.0
    return {"tokens": n, "tps": tps}


class LlamaClient:
    def __init__(
        self,
        base_url: str,
        *,
        request_timeout_s: float,
        connect_timeout_s: float,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(request_timeout_s, connect=connect_timeout_s),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/health")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def chat(
        self,
        *,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float,
        top_p: float,
        max_tokens: int,
        model: str = "opsgpt",
    ) -> dict:
        """Non-streaming completion. Returns the assistant message dict
        (may contain `tool_calls`). Used by the tool-calling orchestrator."""
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            resp = await self._client.post("/v1/chat/completions", json=payload)
            if resp.status_code != 200:
                raise LlamaClientError(
                    f"upstream returned {resp.status_code}: {resp.text[:500]}"
                )
            data = resp.json()
            return data["choices"][0]["message"]
        except httpx.HTTPError as exc:
            raise LlamaClientError(f"failed to reach inference server: {exc}") from exc

    async def complete_openai(self, payload: dict) -> dict:
        """Forward an OpenAI chat-completion request verbatim and return the full
        upstream JSON (id/choices/usage). Used by the public /v1 API (non-stream)."""
        try:
            resp = await self._client.post("/v1/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise LlamaClientError(f"failed to reach inference server: {exc}") from exc
        if resp.status_code != 200:
            raise LlamaClientError(f"upstream returned {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    async def stream_openai(self, payload: dict) -> AsyncIterator[str]:
        """Forward a streaming OpenAI request, yielding each upstream SSE data
        payload (the JSON string after 'data:'); '[DONE]' is yielded as-is."""
        try:
            async with self._client.stream(
                "POST", "/v1/chat/completions", json=payload
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise LlamaClientError(f"upstream {resp.status_code}: {body[:500]}")
                async for line in resp.aiter_lines():
                    if line.startswith("data:"):
                        yield line[5:].strip()
        except httpx.HTTPError as exc:
            raise LlamaClientError(f"failed to reach inference server: {exc}") from exc

    async def stream_chat_tools(
        self,
        *,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        top_p: float,
        max_tokens: int,
        model: str = "opsgpt",
    ) -> AsyncIterator[tuple[str, object]]:
        """Streaming completion WITH tools. Yields:
            ("reasoning", str) | ("content", str) | ("tool_calls", list[dict])
        Content/reasoning stream live; assembled tool_calls are emitted once at end.
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "tools": tools,
            "tool_choice": "auto",
        }
        acc: dict[int, dict] = {}
        timings: dict | None = None
        try:
            async with self._client.stream(
                "POST", "/v1/chat/completions", json=payload
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise LlamaClientError(f"upstream {resp.status_code}: {body[:500]}")
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = orjson.loads(data)
                    except orjson.JSONDecodeError:
                        continue
                    if chunk.get("timings"):
                        timings = chunk["timings"]
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    if delta.get("reasoning_content"):
                        yield ("reasoning", delta["reasoning_content"])
                    if delta.get("content"):
                        yield ("content", delta["content"])
                    for tc in delta.get("tool_calls") or []:
                        idx = tc.get("index", 0)
                        slot = acc.setdefault(
                            idx,
                            {"id": "", "type": "function",
                             "function": {"name": "", "arguments": ""}},
                        )
                        if tc.get("id"):
                            slot["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            slot["function"]["name"] = fn["name"]
                        if fn.get("arguments"):
                            slot["function"]["arguments"] += fn["arguments"]
        except httpx.HTTPError as exc:
            raise LlamaClientError(f"failed to reach inference server: {exc}") from exc

        if acc:
            yield ("tool_calls", [acc[i] for i in sorted(acc)])
        if timings:
            yield ("stats", _stats_from_timings(timings))

    async def stream_chat(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float,
        top_p: float,
        max_tokens: int,
        model: str = "opsgpt",
    ) -> AsyncIterator[tuple[str, object]]:
        """Yield (kind, payload) events as they arrive.
        kind is "reasoning"|"content" (payload str) or "stats" (payload dict).

        Hybrid reasoning models (Qwen3, X-Coder) stream their <think> phase in
        the OpenAI `reasoning_content` delta field and the answer in `content`.
        We surface both, tagged, so the UI can render thinking separately.
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }
        timings: dict | None = None
        try:
            async with self._client.stream(
                "POST", "/v1/chat/completions", json=payload
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise LlamaClientError(
                        f"upstream returned {resp.status_code}: {body[:500]}"
                    )
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = orjson.loads(data)
                    except orjson.JSONDecodeError:
                        continue
                    if chunk.get("timings"):
                        timings = chunk["timings"]
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    reasoning = delta.get("reasoning_content")
                    if reasoning:
                        yield ("reasoning", reasoning)
                    content = delta.get("content")
                    if content:
                        yield ("content", content)
        except httpx.HTTPError as exc:  # network/timeout/connection errors
            raise LlamaClientError(f"failed to reach inference server: {exc}") from exc

        if timings:
            yield ("stats", _stats_from_timings(timings))
