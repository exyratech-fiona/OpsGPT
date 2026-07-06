"""Streaming chat endpoint.

The browser POSTs a conversation; we resolve the OpsGPT mode, prepend the right
system prompt, and stream the assistant's tokens back as Server-Sent Events.

Event protocol (each is a single SSE `data:` line with a JSON object):
    {"type": "meta",  "mode": "...", "model": "...", "display_name": "..."}
    {"type": "token", "content": "..."}              (many)
    {"type": "error", "message": "..."}              (on failure)
    {"type": "done"}                                 (always last on success)
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

import orjson
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core import metrics
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import get_db
from app.db.models import User
from app.schemas.chat import ChatRequest, ModeInfo
from app.services import mcp_service, rag, ratelimit, user_service
from app.services.embed_client import EmbedError
from app.services.llama_client import LlamaClientError
from app.services.router import ModeRouter
from app.tools.base import ToolRegistry
from app.tools.orchestrator import run_tool_loop

logger = get_logger(__name__)
router = APIRouter(tags=["chat"])

# A provider's tools are only attached when the message looks relevant (by the
# provider TYPE's keywords) — keeps casual chat fast (tool schemas add ~2k
# prompt tokens). Relevance patterns live in mcp_service.RELEVANCE.


def _sse(obj: dict[str, object]) -> str:
    return f"data: {orjson.dumps(obj).decode('utf-8')}\n\n"


@router.get("/modes", response_model=list[ModeInfo])
async def list_modes() -> list[ModeInfo]:
    """Expose the available OpsGPT modes to the UI (model indicator, etc.)."""
    return [
        ModeInfo(
            id=r.mode,
            display_name=r.display_name,
            model=r.model,
            description=r.description,
        )
        for r in ModeRouter.routes()
    ]


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    settings = get_settings()
    mode_router: ModeRouter = request.app.state.router
    clients: dict = request.app.state.llama_clients

    last_user = next(
        (m.content for m in reversed(req.messages) if m.role == "user"),
        req.messages[-1].content,
    )
    # Relevance is judged over a WINDOW of the recent turns, not just the last
    # message — so a tool conversation isn't dropped when a follow-up that only
    # supplies a parameter ("in group X there is project Y") lacks a keyword.
    relevance_text = " ".join(
        m.content for m in req.messages[-8:] if m.role in ("user", "assistant")
    ) or last_user
    route = mode_router.resolve(req.mode, last_user)
    # Phase 5: pick the model server for this mode (Chat/Docs->Qwen3,
    # Think->Phi-4, Code->X-Coder). Falls back to the primary client.
    llama = clients.get(route.model, request.app.state.llama)
    # Tools always run on Qwen3 (most reliable tool-caller).
    tool_llama = clients.get("qwen3-8b", request.app.state.llama)

    over_quota = user_service.is_over_quota(user)
    user_id = user.id

    # Per-user rate limit (admins exempt; fails open if Redis is down).
    rate_ok, retry_after = True, 0
    if user.role != "admin":
        rate_ok, retry_after = await ratelimit.check_and_increment(
            getattr(request.app.state, "redis", None),
            str(user.id),
            settings.rate_limit_per_min,
            60,
        )

    # Resolve which tool providers to use: explicit request (MCP panel) wins,
    # otherwise the route's own tools (e.g. ops-cluster). Build a merged registry.
    # DB-backed MCP servers: {name: {"type": .., "registry": ToolRegistry}}.
    mcp_servers: dict = getattr(request.app.state, "mcp", {})
    # candidate servers: those the request enabled, else all configured
    requested_names = req.tool_providers if req.tool_providers else list(mcp_servers)
    registry: ToolRegistry | None = None
    active_types: list[str] = []
    active_entries: list[dict] = []
    if requested_names:
        merged = ToolRegistry()
        for name in requested_names:
            entry = mcp_servers.get(name)
            if not entry:
                continue
            # only attach if the recent conversation is relevant to this provider type
            pat = mcp_service.RELEVANCE.get(entry["type"])
            if pat is not None and not pat.search(relevance_text):
                continue
            if entry["type"] not in active_types:
                active_types.append(entry["type"])
            active_entries.append(entry)
            for tool in entry["registry"].all_tools():
                merged.register(tool)
        if len(merged):
            registry = merged

    # Build the upstream message list: our system prompt + the conversation
    # (drop any client-sent system messages so the route prompt is authoritative).
    # When tools are active we leave the /think|/no_think switch off so the model
    # is free to reason about which tool to call.
    if registry is not None:
        # /no_think keeps simple turns fast; the model still emits tool_calls
        # when a question actually needs live data.
        hint_parts = [
            mcp_service.TOOL_HINTS[t] for t in active_types if t in mcp_service.TOOL_HINTS
        ]
        # Per-connection GitLab hints: default project + known/favorite projects,
        # so "show recent pipelines" works without the user naming a project.
        for entry in active_entries:
            if entry["type"] != "gitlab":
                continue
            gcfg = entry.get("config") or {}
            default_project = str(gcfg.get("default_project") or "").strip()

            def _refs(v: object) -> list[str]:
                if isinstance(v, list):
                    return [str(x).strip() for x in v if str(x).strip()]
                return [p.strip() for p in re.split(r"[\n,]", str(v or "")) if p.strip()]

            proj_list = _refs(gcfg.get("projects")) or _refs(gcfg.get("favorites"))
            if not default_project and proj_list:
                default_project = proj_list[0]
            if default_project:
                hint_parts.append(
                    f"The default GitLab project is '{default_project}'; use it when "
                    "the user doesn't name a project."
                )
            if proj_list:
                hint_parts.append(
                    "Configured GitLab projects: " + ", ".join(proj_list[:10]) + ". "
                    "When the user asks about 'the latest pipeline(s)' or overall CI status "
                    "without naming one, call gl_latest_pipelines to report all of them."
                )
        hints = "".join("\n" + h for h in hint_parts)
        system_prompt = route.system_prompt + (
            "\n\nYou have live read-only tools available. Only call a tool when the "
            "question needs real data; for casual messages just reply directly. "
            "Prefer calling a tool over telling the user how to do it themselves. "
            "After using a tool, answer concisely." + hints + "\n/no_think"
        )
    elif route.model == "phi-4-mini":
        # Phi-4 is not Qwen-family; the /think|/no_think switches are meaningless
        # to it, so don't pollute its prompt.
        system_prompt = route.system_prompt
    else:
        system_prompt = route.system_prompt + (
            "\n/think" if route.thinking else "\n/no_think"
        )
    upstream_messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt}
    ]
    upstream_messages.extend(
        {"role": m.role, "content": m.content}
        for m in req.messages
        if m.role != "system"
    )

    temperature = req.temperature if req.temperature is not None else route.temperature
    top_p = req.top_p if req.top_p is not None else settings.default_top_p
    max_tokens = req.max_tokens or settings.default_max_tokens

    # --- RAG retrieval (ops-docs): pull relevant chunks and inject as context ---
    citations: list[dict] = []
    if route.mode == "ops-docs":
        embed = request.app.state.rag_embed
        try:
            results = await rag.retrieve(
                db,
                embed,
                user_id=user.id,
                query=last_user,
                top_k=settings.rag_top_k,
                document_ids=req.document_ids,
                redis=getattr(request.app.state, "redis", None),
                reranker=getattr(request.app.state, "reranker", None),
                candidates=settings.rag_rerank_candidates,
            )
        except EmbedError:
            results = []
        if results:
            context, citations = rag.build_context(results)
            upstream_messages.append(
                {
                    "role": "system",
                    "content": (
                        "Answer the user's question using ONLY the context below. "
                        "If the answer is not in it, say you couldn't find it in the "
                        "documents. Cite sources inline as [1], [2], etc.\n\n"
                        f"CONTEXT:\n{context}"
                    ),
                }
            )
        else:
            upstream_messages.append(
                {
                    "role": "system",
                    "content": (
                        "There is no relevant document context available. Tell the "
                        "user you couldn't find relevant information in their uploaded "
                        "documents."
                    ),
                }
            )

    async def event_stream() -> AsyncIterator[str]:
        yield _sse(
            {
                "type": "meta",
                "mode": route.mode,
                "model": route.model,
                "display_name": route.display_name,
                "tools": bool(registry),
            }
        )

        if citations:
            yield _sse({"type": "citations", "items": citations})

        # --- per-user rate limit ---
        if not rate_ok:
            yield _sse(
                {
                    "type": "error",
                    "message": f"Rate limit reached. Please wait {retry_after}s "
                    "before sending another message.",
                }
            )
            yield _sse({"type": "done"})
            return

        # --- per-user daily token quota ---
        if over_quota:
            yield _sse(
                {
                    "type": "error",
                    "message": "You've reached your daily token limit. "
                    "Please try again tomorrow or ask an admin to raise it.",
                }
            )
            yield _sse({"type": "done"})
            return

        # --- agentic tool-calling path (always Qwen3) ---
        if registry is not None:
            metrics.record_chat(route.mode, "qwen3-8b")
            async for event in run_tool_loop(
                llama=tool_llama,
                registry=registry,
                messages=upstream_messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=settings.tools_max_tokens,
                model="qwen3-8b",
            ):
                etype = event.get("type")
                if etype == "tool_call":
                    metrics.record_tool_call(str(event.get("name", "")))
                elif etype == "stats":
                    tok = int(event.get("tokens", 0))
                    metrics.record_tokens("qwen3-8b", tok)
                    await user_service.record_usage(user_id, tok)
                yield _sse(event)
            return

        # --- plain streaming path ---
        metrics.record_chat(route.mode, route.model)
        try:
            async for kind, delta in llama.stream_chat(
                messages=upstream_messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                model=route.model,
            ):
                if kind == "reasoning":
                    yield _sse({"type": "reasoning", "content": delta})
                elif kind == "stats":
                    tok = int(delta.get("tokens", 0))
                    metrics.record_tokens(route.model, tok)
                    await user_service.record_usage(user_id, tok)
                    yield _sse({"type": "stats", **delta})
                else:
                    yield _sse({"type": "token", "content": delta})
            yield _sse({"type": "done"})
        except LlamaClientError as exc:
            logger.error("inference_failed", extra={"error": str(exc), "mode": route.mode})
            yield _sse({"type": "error", "message": "Inference failed. Please retry."})
        except Exception:  # pragma: no cover - defensive catch-all for the stream
            logger.exception("stream_crashed")
            yield _sse({"type": "error", "message": "Unexpected server error."})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering (nginx)
        },
    )
