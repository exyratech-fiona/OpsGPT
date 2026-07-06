"""OpenAI-compatible public API (`/v1`).

Lets external apps/SDKs call the OpsGPT models with an `opsk_` API key exactly
like the OpenAI API:

    from openai import OpenAI
    client = OpenAI(base_url="https://opsgpt.example.com/v1", api_key="opsk_…")
    client.chat.completions.create(model="opsgpt", messages=[...])

Auth accepts both `opsk_` API keys and UI JWTs (see deps.get_current_user).
Per-user daily token quota and per-minute rate limit are enforced here too, and
generated tokens are recorded against the caller's usage.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator

import orjson
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import User
from app.services import ratelimit, user_service
from app.services.embed_client import EmbedError
from app.services.llama_client import LlamaClientError

logger = get_logger(__name__)
router = APIRouter(tags=["OpenAI-compatible API"])

# Shows the "Authorize" padlock in Swagger so a key can be pasted and tried.
_bearer = HTTPBearer(auto_error=False)

# Friendly aliases -> the internal model-server key.
MODEL_ALIASES = {
    "opsgpt": "qwen3-8b", "ops-chat": "qwen3-8b", "chat": "qwen3-8b",
    "qwen3-8b": "qwen3-8b", "qwen3": "qwen3-8b", "qwen": "qwen3-8b",
    "ops-think": "phi-4-mini", "think": "phi-4-mini", "phi-4-mini": "phi-4-mini", "phi": "phi-4-mini",
    "ops-code": "x-coder", "code": "x-coder", "x-coder": "x-coder", "coder": "x-coder",
}
PUBLIC_MODELS = ["opsgpt", "qwen3-8b", "phi-4-mini", "x-coder"]


def _resolve_model(name: str | None) -> str:
    return MODEL_ALIASES.get((name or "").strip().lower(), "qwen3-8b")


class EmbeddingsRequest(BaseModel):
    input: str | list[str]
    model: str = Field(default="nomic", description="embedding model: 'nomic' (768-dim) or 'bge' (BGE-large-en-v1.5, 1024-dim)")
    model_config = ConfigDict(extra="ignore")


class RerankRequest(BaseModel):
    query: str = Field(examples=["data retention policy"])
    documents: list[str] = Field(description="candidate texts to score against the query")
    model: str = Field(default="bge-reranker-v2-m3")
    top_n: int | None = Field(default=None, description="return only the best N (default: all)")
    model_config = ConfigDict(extra="ignore")


class ChatMessage(BaseModel):
    role: str = Field(examples=["user"], description="system | user | assistant")
    content: str | None = Field(default=None, examples=["Explain a Kubernetes rolling update."])


class ChatCompletionRequest(BaseModel):
    model: str = Field(
        default="opsgpt",
        description="opsgpt/ops-chat/qwen3-8b · ops-think/phi-4-mini · ops-code/x-coder",
    )
    messages: list[ChatMessage]
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)
    stream: bool = False
    stop: list[str] | str | None = None
    seed: int | None = None
    model_config = ConfigDict(extra="ignore")


@router.get("/models", summary="List available models")
async def list_models(
    request: Request, user: User = Depends(get_current_user), _c=Depends(_bearer)
) -> dict:
    ids = list(PUBLIC_MODELS) + ["nomic"]
    if getattr(request.app.state, "embed_bge", None) is not None:
        ids.append("bge-large-en-v1.5")
    if getattr(request.app.state, "reranker", None) is not None:
        ids.append("bge-reranker-v2-m3")
    return {
        "object": "list",
        "data": [
            {"id": m, "object": "model", "created": 0, "owned_by": "opsgpt"}
            for m in ids
        ],
    }


@router.post("/chat/completions", summary="Create a chat completion (OpenAI-compatible)")
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    user: User = Depends(get_current_user),
    _c=Depends(_bearer),
):
    settings = get_settings()
    clients: dict = request.app.state.llama_clients
    model_key = _resolve_model(body.model)
    client = clients.get(model_key, request.app.state.llama)

    # --- quota + rate limit (admins exempt from rate limit) ---
    if user_service.is_over_quota(user):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Daily token limit reached.")
    if user.role != "admin":
        ok, retry = await ratelimit.check_and_increment(
            getattr(request.app.state, "redis", None), str(user.id),
            settings.rate_limit_per_min, 60,
        )
        if not ok:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Rate limit reached. Retry in {retry}s.",
            )

    temperature = body.temperature if body.temperature is not None else getattr(settings, "default_temperature", 0.7)
    top_p = body.top_p if body.top_p is not None else settings.default_top_p
    max_tokens = body.max_tokens or settings.default_max_tokens
    payload: dict = {
        "model": model_key,
        "messages": [{"role": m.role, "content": m.content or ""} for m in body.messages],
        "stream": body.stream,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
    }
    if body.stop:
        payload["stop"] = body.stop
    if body.seed is not None:
        payload["seed"] = body.seed

    if not body.stream:
        try:
            data = await client.complete_openai(payload)
        except LlamaClientError as exc:
            logger.error("v1_completion_failed", extra={"error": str(exc)})
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Inference backend failed.")
        usage = data.get("usage") or {}
        toks = int(usage.get("completion_tokens") or 0)
        if toks:
            await user_service.record_usage(user.id, toks)
        data["model"] = body.model or model_key  # echo what the caller asked for
        data.pop("timings", None)  # drop llama.cpp-specific field (keep response clean)
        return JSONResponse(data)

    async def event_stream() -> AsyncIterator[str]:
        total = 0
        uid = user.id
        try:
            async for raw in client.stream_openai(payload):
                if not raw or raw == "[DONE]":
                    continue
                try:
                    chunk = orjson.loads(raw)
                except orjson.JSONDecodeError:
                    continue
                t = chunk.get("timings")
                if t and t.get("predicted_n"):
                    total = int(t["predicted_n"])
                chunk["model"] = body.model or model_key
                # don't leak llama.cpp timings in the public stream
                chunk.pop("timings", None)
                yield f"data: {orjson.dumps(chunk).decode()}\n\n"
        except LlamaClientError as exc:
            logger.error("v1_stream_failed", extra={"error": str(exc)})
            err = {"error": {"message": "Inference backend failed.", "type": "server_error"}}
            yield f"data: {orjson.dumps(err).decode()}\n\n"
        finally:
            if total:
                await user_service.record_usage(uid, total)
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/embeddings", summary="Create embeddings (OpenAI-compatible)")
async def embeddings(
    body: EmbeddingsRequest,
    request: Request,
    user: User = Depends(get_current_user),
    _c=Depends(_bearer),
) -> dict:
    if user_service.is_over_quota(user):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Daily token limit reached.")
    inputs = [body.input] if isinstance(body.input, str) else list(body.input)
    inputs = [str(x) for x in inputs][:256]
    if not inputs:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "'input' must not be empty.")

    # Route to the requested embedding model. Anything starting "bge" -> the
    # BGE-large-en-v1.5 server (if configured); otherwise the default nomic model.
    model_l = (body.model or "nomic").strip().lower()
    if model_l.startswith("bge"):
        client = getattr(request.app.state, "embed_bge", None)
        if client is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "The 'bge' embedding model is not configured on this server.",
            )
        model_name = "bge-large-en-v1.5"
    else:
        client = request.app.state.embed
        model_name = "nomic"

    try:
        vectors = await client.embed(inputs)
    except EmbedError as exc:
        logger.error("v1_embed_failed", extra={"error": str(exc), "model": model_name})
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Embedding backend failed.")
    return {
        "object": "list",
        "model": model_name,
        "data": [
            {"object": "embedding", "index": i, "embedding": v}
            for i, v in enumerate(vectors)
        ],
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


@router.post("/rerank", summary="Rerank documents by relevance to a query (cross-encoder)")
async def rerank(
    body: RerankRequest,
    request: Request,
    user: User = Depends(get_current_user),
    _c=Depends(_bearer),
) -> dict:
    if user_service.is_over_quota(user):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Daily token limit reached.")
    rr = getattr(request.app.state, "reranker", None)
    if rr is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Reranker is not configured on this server.")
    docs = [str(d) for d in body.documents][:100]
    if not docs:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "'documents' must not be empty.")
    try:
        pairs = await rr.rerank(body.query, docs, top_n=body.top_n)
    except Exception as exc:  # noqa: BLE001
        logger.error("v1_rerank_failed", extra={"error": str(exc)})
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Reranker backend failed.")
    return {
        "object": "list",
        "model": "bge-reranker-v2-m3",
        "results": [
            {"index": idx, "relevance_score": score, "document": docs[idx]}
            for idx, score in pairs
        ],
    }
