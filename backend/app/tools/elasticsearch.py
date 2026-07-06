"""Read-only Elasticsearch tools, parameterised by a connection config dict:
    {url, username, password, api_key, verify_tls}
Only GET / _search / _count are used (no writes/deletes)."""

from __future__ import annotations

import re

import httpx
import orjson

from app.core.logging import get_logger
from app.tools.base import Tool, ToolRegistry

logger = get_logger(__name__)

_INDEX_RE = re.compile(r"^[a-zA-Z0-9_.*\-]{1,255}$")
_MAX_OUTPUT = 6000
_MAX_HITS = 25


def _client(cfg: dict) -> httpx.AsyncClient:
    headers = {}
    auth = None
    if cfg.get("api_key"):
        headers["Authorization"] = f"ApiKey {cfg['api_key']}"
    elif cfg.get("username"):
        auth = (cfg["username"], cfg.get("password", ""))
    return httpx.AsyncClient(
        base_url=str(cfg.get("url", "")).rstrip("/"),
        headers=headers,
        auth=auth,
        verify=bool(cfg.get("verify_tls", True)),
        timeout=25.0,
    )


def _trim(t: str) -> str:
    return t[:_MAX_OUTPUT] + "\n… (truncated)" if len(t) > _MAX_OUTPUT else t


async def test_connection(cfg: dict) -> tuple[bool, str]:
    try:
        async with _client(cfg) as c:
            r = await c.get("/_cluster/health")
    except httpx.HTTPError as exc:
        return False, f"connection failed: {exc}"[:300]
    if r.status_code == 401:
        return False, "authentication failed (401)"
    if r.status_code >= 400:
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    try:
        h = r.json()
        return True, f"Connected — cluster '{h.get('cluster_name')}' status {h.get('status')}."
    except ValueError:
        return True, "Connected."


def build_registry(cfg: dict) -> ToolRegistry:
    async def get(path: str, params: dict | None = None) -> str:
        try:
            async with _client(cfg) as c:
                r = await c.get(path, params=params)
        except httpx.HTTPError as exc:
            return f"Elasticsearch error: {exc}"
        if r.status_code >= 400:
            return f"Elasticsearch {r.status_code}: {r.text[:800]}"
        return _trim(r.text)

    async def search(index: str, body: dict) -> str:
        try:
            async with _client(cfg) as c:
                r = await c.post(f"/{index}/_search", json=body)
        except httpx.HTTPError as exc:
            return f"Elasticsearch error: {exc}"
        if r.status_code >= 400:
            return f"Elasticsearch {r.status_code}: {r.text[:800]}"
        try:
            data = r.json()
        except ValueError:
            return _trim(r.text)
        hits = data.get("hits", {})
        total = hits.get("total", {})
        total_n = total.get("value", total) if isinstance(total, dict) else total
        rows = [h.get("_source", h) for h in hits.get("hits", [])]
        return _trim(orjson.dumps({"total": total_n, "returned": len(rows), "hits": rows}).decode())

    async def list_indices(a: dict) -> str:
        pat = a.get("pattern", "")
        path = "/_cat/indices"
        if pat:
            if not _INDEX_RE.match(pat):
                return "Error: invalid 'pattern'."
            path = f"/_cat/indices/{pat}"
        return await get(path, {"format": "json", "h": "health,status,index,docs.count,store.size", "s": "index"})

    async def cluster_health(_: dict) -> str:
        return await get("/_cluster/health")

    async def mapping(a: dict) -> str:
        idx = a.get("index", "")
        if not _INDEX_RE.match(idx):
            return "Error: invalid/missing 'index'."
        return await get(f"/{idx}/_mapping")

    async def count(a: dict) -> str:
        idx = a.get("index", "")
        if not _INDEX_RE.match(idx):
            return "Error: invalid/missing 'index'."
        q = a.get("query")
        body = {"query": {"query_string": {"query": str(q)}}} if q else None
        try:
            async with _client(cfg) as c:
                r = await c.post(f"/{idx}/_count", json=body)
        except httpx.HTTPError as exc:
            return f"Elasticsearch error: {exc}"
        return f"Elasticsearch {r.status_code}: {r.text[:800]}" if r.status_code >= 400 else _trim(r.text)

    async def search_logs(a: dict) -> str:
        idx = a.get("index", "")
        if not _INDEX_RE.match(idx):
            return "Error: invalid/missing 'index'."
        try:
            size = max(1, min(int(a.get("size", 10)), _MAX_HITS))
        except (TypeError, ValueError):
            size = 10
        tf = a.get("time_field", "@timestamp")
        must = []
        if a.get("query"):
            must.append({"query_string": {"query": str(a["query"])}})
        if a.get("last_minutes"):
            try:
                must.append({"range": {tf: {"gte": f"now-{int(a['last_minutes'])}m"}}})
            except (TypeError, ValueError):
                pass
        body = {
            "size": size,
            "query": {"bool": {"must": must}} if must else {"match_all": {}},
            "sort": [{tf: {"order": "desc", "unmapped_type": "date"}}],
        }
        return await search(idx, body)

    reg = ToolRegistry()
    reg.register(Tool("es_list_indices", "List indices (health, docs, size); optional pattern e.g. logs-*.",
                      {"type": "object", "properties": {"pattern": {"type": "string"}}}, list_indices))
    reg.register(Tool("es_cluster_health", "Cluster health (status, nodes, shards).",
                      {"type": "object", "properties": {}}, cluster_health))
    reg.register(Tool("es_index_mapping", "Field mapping (schema) of an index.",
                      {"type": "object", "properties": {"index": {"type": "string"}}, "required": ["index"]}, mapping))
    reg.register(Tool("es_count", "Count docs in an index, optional Lucene query (e.g. level:ERROR).",
                      {"type": "object", "properties": {"index": {"type": "string"}, "query": {"type": "string"}},
                       "required": ["index"]}, count))
    reg.register(Tool("es_search_logs",
                      "Search logs newest-first; Lucene query + optional last_minutes window.",
                      {"type": "object", "properties": {
                          "index": {"type": "string"}, "query": {"type": "string"},
                          "size": {"type": "integer"}, "last_minutes": {"type": "integer"},
                          "time_field": {"type": "string"}}, "required": ["index"]}, search_logs))
    return reg
