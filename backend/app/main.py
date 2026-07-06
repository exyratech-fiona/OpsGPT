"""OpsGPT FastAPI application entrypoint.

Wires configuration, logging, the upstream llama.cpp client, the mode router,
CORS, and the API routers together. The llama client is created once at startup
and shared across requests via app.state.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import __version__
from app.api import admin, auth, chat, docs, gateway_auth, health, keys, mcp, openai_compat, reports
from app.core import metrics
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger, request_id_var
from app.core.redis_client import create_redis
from app.db.base import AsyncSessionLocal, engine
from app.db.models import Role
from app.services import user_service
from app.services.embed_client import EmbedClient
from app.services.reranker_client import RerankerClient
from app.services.llama_client import LlamaClient
from app.services.router import ModeRouter

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger("opsgpt")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One client per model server. Keyed by the model name used in routes.
    def _mk(url: str) -> LlamaClient:
        return LlamaClient(
            url,
            request_timeout_s=settings.request_timeout_s,
            connect_timeout_s=settings.connect_timeout_s,
        )

    app.state.llama_clients = {
        "qwen3-8b": _mk(settings.llamacpp_base_url),
        "phi-4-mini": _mk(settings.model_phi_base_url),
        "x-coder": _mk(settings.model_xcoder_base_url),
    }
    # default / primary client (health checks, tool-calling)
    app.state.llama = app.state.llama_clients["qwen3-8b"]
    app.state.router = ModeRouter(settings)
    app.state.embed = EmbedClient(settings.embed_base_url)
    # Second embedding model (BGE-large-en-v1.5, 1024-dim). BGE convention: no doc
    # prefix, and a retrieval instruction on the query. None when not configured.
    app.state.embed_bge = (
        EmbedClient(
            settings.embed_bge_base_url,
            doc_prefix="",
            query_prefix="Represent this sentence for searching relevant passages: ",
        )
        if settings.embed_bge_base_url
        else None
    )
    # The embedder RAG uses (documents + query). Prefer BGE (1024-dim) when present.
    app.state.rag_embed = app.state.embed_bge or app.state.embed
    # Cross-encoder reranker for RAG (retrieve-20 -> rerank -> top-5). None if unset.
    app.state.reranker = (
        RerankerClient(settings.reranker_base_url) if settings.reranker_base_url else None
    )
    app.state.redis = await create_redis()

    # Configurable MCP tool providers (DB-backed). Seed from legacy env config
    # on first run, then build runtime registries from the mcp_servers table.
    from app.services import mcp_service

    app.state.mcp = {}
    await mcp_service.seed_from_env(app)
    await mcp_service.ensure_seed_grc(app)
    await mcp_service.load_registries(app)

    # Background failure-scan refresh (GitLab + K8s) feeding the reports cache.
    from app.services import alert_service, report_service

    # Verify critical dependencies are reachable before serving traffic, so an
    # orchestrator never routes to an instance that will fail every request.
    await _verify_dependencies()

    app.state.report_cache = None
    app.state.delivery_cache = None
    app.state.report_task = asyncio.create_task(report_service.background_refresh(app))
    app.state.delivery_task = asyncio.create_task(
        report_service.background_delivery_refresh(app)
    )
    app.state.digest_task = asyncio.create_task(report_service.background_digest(app))
    app.state.alert_task = asyncio.create_task(alert_service.background_monitor(app))

    await _seed_admin()
    # Note: do NOT log secrets or PII (admin email) here.
    logger.info("startup", extra={"version": __version__, "env": settings.environment})
    try:
        yield
    finally:
        for attr in ("report_task", "delivery_task", "digest_task", "alert_task"):
            task = getattr(app.state, attr, None)
            if task is not None:
                task.cancel()
        for client in app.state.llama_clients.values():
            await client.aclose()
        await app.state.embed.aclose()
        if getattr(app.state, "embed_bge", None) is not None:
            await app.state.embed_bge.aclose()
        if getattr(app.state, "reranker", None) is not None:
            await app.state.reranker.aclose()
        if app.state.redis is not None:
            await app.state.redis.aclose()
        await engine.dispose()
        logger.info("shutdown")


async def _verify_dependencies(retries: int = 5, delay_s: float = 2.0) -> None:
    """Block startup until Postgres is reachable (a few retries for slow boots).

    Redis is best-effort (the app degrades gracefully if it's down), so we warn
    but don't fail on Redis.
    """
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            last_exc = None
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("db_not_ready", extra={"attempt": attempt, "error": str(exc)[:200]})
            await asyncio.sleep(delay_s)
    if last_exc is not None:
        raise RuntimeError(f"database unreachable after {retries} attempts") from last_exc


async def _seed_admin() -> None:
    """Create the seed admin on first run (empty users table) if configured."""
    if not settings.admin_password:
        return
    async with AsyncSessionLocal() as db:
        if await user_service.count_users(db) > 0:
            return
        await user_service.create_user(
            db, settings.admin_email, settings.admin_password, role=Role.admin.value
        )
        await db.commit()
        logger.info("admin_seeded", extra={"email": settings.admin_email})


app = FastAPI(
    title="OpsGPT API",
    version=__version__,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _request_context_middleware(request: Request, call_next):
    # Correlation id: honor an inbound X-Request-ID (from the edge) or mint one,
    # expose it on logs (via contextvar) and echo it back to the client.
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    token = request_id_var.set(rid)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    # use the matched route template (not the raw URL) to bound cardinality
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    elapsed = time.perf_counter() - start
    metrics.HTTP_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    metrics.HTTP_LATENCY.labels(path).observe(elapsed)
    response.headers["X-Request-ID"] = rid
    return response


@app.get("/metrics")
async def metrics_endpoint() -> Response:
    data, content_type = metrics.render_latest()
    return Response(content=data, media_type=content_type)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(keys.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)
app.include_router(docs.router, prefix=settings.api_prefix)
app.include_router(mcp.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(reports.router, prefix=settings.api_prefix)
# OpenAI-compatible public API at /v1 (nginx forwards /v1/ to the backend).
app.include_router(openai_compat.router, prefix="/v1")
# Gateway token endpoint (POST /auth/token, /v1/token) — username+password -> bearer.
app.include_router(gateway_auth.router)


@app.get("/api")
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "version": __version__, "status": "ok"}
