"""Configurable MCP / tool-provider management.

Tool providers (Kubernetes, Elasticsearch, GitLab) are stored in the DB as
McpServer rows. This service builds runtime tool registries from those rows,
tests connections, and seeds from the legacy env config on first run.
"""

from __future__ import annotations

import os
import re

from sqlalchemy import func, select

from app.core import netguard
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import AsyncSessionLocal
from app.db.models import McpServer
from app.tools import elasticsearch as es_provider
from app.tools import gitlab as gl_provider
from app.tools import grc as grc_provider
from app.tools import kubernetes as k8s_provider
from app.tools.base import ToolRegistry

logger = get_logger(__name__)
settings = get_settings()

PROVIDER_TYPES = ("kubernetes", "elasticsearch", "gitlab", "grc")

DISPLAY = {
    "kubernetes": "Kubernetes",
    "elasticsearch": "Elasticsearch",
    "gitlab": "GitLab",
    "grc": "GRC / Compliance",
}

# Keyword gate per type: tools only attach when the message looks relevant.
RELEVANCE: dict[str, re.Pattern] = {
    "kubernetes": re.compile(
        r"\b(k8s|kube|kubernetes|kubectl|pod|pods|namespace|namespaces|ns|deployment|"
        r"deploy|replica|service|svc|ingress|node|nodes|cluster|crashloop|oomkill|pvc|"
        r"configmap|secret|daemonset|statefulset|container|helm|rollout|hpa|event|events|log|logs)\b",
        re.IGNORECASE,
    ),
    "elasticsearch": re.compile(
        r"\b(elastic|elasticsearch|\bes\b|kibana|index|indices|log|logs|error|errors|"
        r"exception|stacktrace|query|search|document|docs|shard|shards|@timestamp)\b",
        re.IGNORECASE,
    ),
    "gitlab": re.compile(
        r"\b(gitlab|git|pipeline|pipelines|ci|cd|ci/cd|job|jobs|runner|merge request|mr|"
        r"\bmrs?\b|commit|branch|repo|repository|project|projects|group|groups|build|"
        r"builds|deploy|stage|failed|failing|trace)\b",
        re.IGNORECASE,
    ),
    "grc": re.compile(
        r"\b(grc|ssp|control|controls|compliance|compliant|non-?compliant|posture|"
        r"benchmark|\bcis\b|catalog|scan|scanned|evidence|finding|findings|remediat\w*|"
        r"audit|passed|failed|not applicable|asset|assets|server|hardening|"
        r"trmg|im8|vulnerabilit\w*)\b",
        re.IGNORECASE,
    ),
}

# Short, provider-type-specific guidance appended to the system prompt when that
# provider's tools are attached. Keeps the model from guessing API details.
TOOL_HINTS: dict[str, str] = {
    "gitlab": (
        "GitLab: a 'project' may be a numeric id, a full path "
        "(group/subgroup/project) or a pasted GitLab URL. Projects are often nested "
        "several groups deep, so do NOT guess the path — when the user names a project "
        "but you don't have its exact id, call gl_list_projects with a search term "
        "first, then use the returned numeric id for the other tools. For a general "
        "'latest pipelines' / overall CI status question, call gl_latest_pipelines."
    ),
    "kubernetes": (
        "Kubernetes access is read-only (the 'view' role); you cannot change anything."
    ),
    "elasticsearch": (
        "Elasticsearch access is read-only (search/count only)."
    ),
    "grc": (
        "IMPORTANT: In this system, 'SSP' means a published System Security Plan stored "
        "in Elasticsearch (grc-ssp-published-*) — NOT a generic industry acronym. Words "
        "like SSP, control, compliance, asset, scan, evidence ALWAYS refer to THIS "
        "system's data. NEVER answer these from general knowledge or list unrelated "
        "meanings — ALWAYS call a grc_* tool first and answer only from its result. "
        "For 'the latest SSP' or 'list SSPs' call grc_list_ssps (returns them "
        "newest-first with published_at; the first item is the latest). "
        "Data lives in 3 index families: SSP inputs (grc-ssp-published-<env>), per-asset "
        "scan RESULTS (<uuid>-<env>, newest doc = current), and RAW evidence "
        "(grc-raw-<uuid>-<env>). Do NOT write ES queries yourself — use the grc_* tools. "
        "An 'asset' may be a hostname (e.g. router-01) or an asset_uuid; if unsure, call "
        "grc_list_assets first. Environments are dev/sit/demo/local/uat. control_status "
        "is passed / failed / not applicable(passed) / not-run(null); "
        "'not applicable(passed)' counts as compliant."
    ),
}

_KUBE_DIR = "/tmp/opsgpt-kube"

# Config keys that are secrets — masked in API responses, preserved on update.
SECRET_FIELDS = {"kubeconfig", "password", "api_key", "token"}


def public_config(config: dict) -> dict:
    """Copy of config with secret values blanked (for sending to the UI)."""
    out = {}
    for k, v in (config or {}).items():
        if k in SECRET_FIELDS:
            out[k] = ""  # never expose secrets
            out[f"{k}_set"] = bool(v)
        else:
            out[k] = v
    return out


def merge_config(existing: dict, update: dict) -> dict:
    """Merge an update into existing config; blank secret fields keep their value."""
    result = dict(existing or {})
    for k, v in (update or {}).items():
        if k.endswith("_set"):
            continue
        if k in SECRET_FIELDS and (v is None or v == ""):
            continue  # keep existing secret
        result[k] = v
    return result


def tools_of(server) -> list[dict]:
    """Build the registry just to list tool names/descriptions for the UI."""
    try:
        reg = build_registry_for(server)
    except Exception:  # noqa: BLE001
        return []
    if not reg:
        return []
    return [{"name": t.name, "description": t.description} for t in reg.all_tools()]


def _write_kubeconfig(key: str, content: str) -> str:
    os.makedirs(_KUBE_DIR, exist_ok=True)
    path = os.path.join(_KUBE_DIR, f"{key}.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content or "")
    os.chmod(path, 0o600)
    return path


def build_registry_for(server: McpServer) -> ToolRegistry | None:
    cfg = server.config or {}
    if server.provider_type == "kubernetes":
        path = _write_kubeconfig(str(server.id), cfg.get("kubeconfig", ""))
        return k8s_provider.build_registry(path)
    if server.provider_type == "elasticsearch":
        return es_provider.build_registry(cfg)
    if server.provider_type == "gitlab":
        return gl_provider.build_registry(cfg)
    if server.provider_type == "grc":
        return grc_provider.build_registry(cfg)
    return None


def assert_config_url_safe(provider_type: str, cfg: dict) -> None:
    """Raise netguard.UnsafeUrlError if the provider URL must be blocked (SSRF)."""
    if provider_type in ("elasticsearch", "gitlab", "grc"):
        url = str(cfg.get("url", "")).strip()
        if url:
            netguard.assert_safe_url(url)


async def test_connection(provider_type: str, cfg: dict) -> tuple[bool, str]:
    # SSRF guard: reject provider URLs that resolve to loopback / link-local /
    # cloud-metadata before we ever issue a request. Private LAN ranges are
    # allowed on purpose (internal GitLab/Elasticsearch are the intended targets).
    if provider_type in ("elasticsearch", "gitlab", "grc"):
        url = str(cfg.get("url", "")).strip()
        if url:
            try:
                netguard.assert_safe_url(url)
            except netguard.UnsafeUrlError as exc:
                return False, f"Blocked unsafe URL: {exc}"
    if provider_type == "kubernetes":
        path = _write_kubeconfig("test", cfg.get("kubeconfig", ""))
        return await k8s_provider.test_connection(path)
    if provider_type == "elasticsearch":
        return await es_provider.test_connection(cfg)
    if provider_type == "gitlab":
        return await gl_provider.test_connection(cfg)
    if provider_type == "grc":
        return await grc_provider.test_connection(cfg)
    return False, f"unknown provider type '{provider_type}'"


async def load_registries(app) -> None:
    """(Re)build app.state.mcp = {name: {"type": .., "registry": ToolRegistry}}."""
    registry_map: dict[str, dict] = {}
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(select(McpServer).where(McpServer.enabled.is_(True)))
        ).scalars().all()
        for s in rows:
            try:
                reg = build_registry_for(s)
                if reg and len(reg):
                    registry_map[s.name] = {
                        "type": s.provider_type,
                        "registry": reg,
                        "config": s.config or {},
                    }
            except Exception as exc:  # noqa: BLE001
                logger.error("mcp_build_failed", extra={"server": s.name, "error": str(exc)})
    app.state.mcp = registry_map
    logger.info("mcp_loaded", extra={"servers": list(registry_map)})


async def seed_from_env(app) -> None:
    """First-run migration: create McpServer rows from legacy env config."""
    async with AsyncSessionLocal() as db:
        count = (await db.execute(select(func.count()).select_from(McpServer))).scalar_one()
        if count:
            return
        seeded: list[str] = []
        if settings.tools_kubernetes_enabled and os.path.exists(settings.tools_kubeconfig):
            with open(settings.tools_kubeconfig, encoding="utf-8") as f:
                kube = f.read()
            db.add(McpServer(name="Kubernetes", provider_type="kubernetes",
                             config={"kubeconfig": kube}, enabled=True, status="ok"))
            seeded.append("Kubernetes")
        if settings.es_url:
            db.add(McpServer(name="Elasticsearch", provider_type="elasticsearch",
                             config={"url": settings.es_url, "username": settings.es_username,
                                     "password": settings.es_password, "api_key": settings.es_api_key,
                                     "verify_tls": settings.es_verify_tls},
                             enabled=True, status="ok"))
            seeded.append("Elasticsearch")
        if seeded:
            await db.commit()
            logger.info("mcp_seeded", extra={"servers": seeded})


async def ensure_seed_grc(app) -> None:
    """Idempotently add a 'GRC / Compliance' provider that reuses the existing
    Elasticsearch connection, so the compliance Q&A tools are available without
    the admin re-entering ES credentials. No-op once a grc server exists."""
    async with AsyncSessionLocal() as db:
        has_grc = (
            await db.execute(
                select(func.count()).select_from(McpServer).where(McpServer.provider_type == "grc")
            )
        ).scalar_one()
        if has_grc:
            return
        es = (
            await db.execute(
                select(McpServer).where(McpServer.provider_type == "elasticsearch").limit(1)
            )
        ).scalar_one_or_none()
        base = dict(es.config) if es and es.config else None
        if base is None and settings.es_url:
            base = {"url": settings.es_url, "username": settings.es_username,
                    "password": settings.es_password, "api_key": settings.es_api_key,
                    "verify_tls": settings.es_verify_tls}
        if not base:
            return  # no ES connection to clone; admin can add GRC manually
        base["env"] = ""  # default env resolved per-query (dev unless asked otherwise)
        db.add(McpServer(name="GRC Compliance", provider_type="grc", config=base,
                         enabled=True, status="ok",
                         status_message="Auto-configured from Elasticsearch connection."))
        await db.commit()
        logger.info("mcp_grc_seeded")
