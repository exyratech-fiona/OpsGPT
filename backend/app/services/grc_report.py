"""Aggregations over the GRC ELK indices for the Compliance dashboard + an AI
compliance-officer summary. Reuses the low-level helpers from app.tools.grc and
the Elasticsearch connection stored as an MCP provider (grc, else elasticsearch).
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import httpx
import orjson
from sqlalchemy import select

from app.core.logging import get_logger
from app.db.base import AsyncSessionLocal
from app.db.models import McpServer
from app.services import report_service
from app.tools.grc import _UUID_RE, _bucket, _client, _tally

logger = get_logger(__name__)

_ENVS = ("dev", "sit", "demo", "local", "uat", "preprod", "prod")
CACHE_TTL_S = 300


def _env(env: str | None) -> str:
    e = (env or "dev").strip().lower()
    return e if e in _ENVS else "dev"


def _pct(passed: int, failed: int, na: int) -> float:
    ev = passed + failed + na
    return round((passed + na) / ev * 100, 1) if ev else 0.0


async def _es_config() -> dict | None:
    """Load the ES connection from the GRC provider (falls back to elasticsearch)."""
    async with AsyncSessionLocal() as db:
        for ptype in ("grc", "elasticsearch"):
            row = (
                await db.execute(select(McpServer).where(McpServer.provider_type == ptype).limit(1))
            ).scalar_one_or_none()
            if row and row.config:
                return dict(row.config)
    return None


async def _search(cfg: dict, index: str, body: dict) -> dict:
    async with _client(cfg) as c:
        r = await c.post(f"/{index}/_search", json=body)
    if r.status_code >= 400:
        raise httpx.HTTPStatusError(r.text[:200], request=r.request, response=r)
    return r.json()


async def _latest(cfg: dict, index: str) -> dict | None:
    d = await _search(cfg, index, {"size": 1, "sort": [{"@timestamp": "desc"}],
                                   "query": {"match_all": {}}})
    h = d.get("hits", {}).get("hits", [])
    return h[0]["_source"] if h else None


async def _result_indices(cfg: dict, env: str) -> list[str]:
    async with _client(cfg) as c:
        r = await c.get(f"/_cat/indices/*-{env}", params={"format": "json", "h": "index"})
    if r.status_code >= 400:
        return []
    return sorted(i["index"] for i in r.json()
                  if not i["index"].startswith("grc-") and i["index"].endswith(f"-{env}"))


async def _resolve(cfg: dict, asset: str, env: str) -> tuple[str | None, str | None]:
    m = _UUID_RE.search(asset or "")
    if m:
        u = m.group(0).lower()
        return f"{u}-{env}", u
    try:
        d = await _search(cfg, f"*-{env},-grc-*",
                          {"size": 1, "_source": ["asset.asset_uuid"],
                           "query": {"query_string": {
                               "query": f"asset.asset_id:*{asset}* OR asset.hostname:*{asset}*",
                               "analyze_wildcard": True}}})
    except httpx.HTTPError:
        d = None
    h = (d or {}).get("hits", {}).get("hits", [])
    if h:
        return h[0]["_index"], h[0]["_source"].get("asset", {}).get("asset_uuid")
    return None, None


async def _titles(cfg: dict, uuid: str, env: str) -> dict:
    """control_id -> human title. Linux/OCI/K8s expose raw_data.control_id_map;
    AWS raw docs don't, so fall back to building a map from raw_data.controls[]."""
    try:
        d = await _latest(cfg, f"grc-raw-{uuid}-{env}")
    except httpx.HTTPError:
        return {}
    rd = (d or {}).get("raw_data", {}) or {}
    cim = rd.get("control_id_map") or {}
    if cim:
        return cim
    out: dict = {}
    for c in rd.get("controls", []) or []:
        title = c.get("provides") or c.get("name") or c.get("title") or c.get("description") or ""
        ids = c.get("control_ids") or ([c.get("control_id")] if c.get("control_id") else [])
        for cid in ids:
            if cid and title and cid not in out:
                out[cid] = title
    return out


async def compliance_overview(app, env: str = "dev") -> dict:
    """Fleet compliance posture for one environment (cached in Redis)."""
    env = _env(env)
    redis = getattr(app.state, "redis", None)
    ckey = f"compliance:{env}"
    if redis is not None:
        try:
            blob = await redis.get(ckey)
            if blob:
                return orjson.loads(blob)
        except Exception:  # noqa: BLE001
            pass

    cfg = await _es_config()
    empty = {"env": env, "generated_at": datetime.now(timezone.utc).isoformat(),
             "fleet": {}, "by_platform": [], "bands": {}, "asset_count": 0,
             "assets": [], "ssp_count": 0, "ssps": []}
    if not cfg:
        empty["error"] = "No Elasticsearch/GRC connection configured."
        return empty

    idxs = await _result_indices(cfg, env)
    sem = asyncio.Semaphore(10)

    async def one(idx: str) -> dict | None:
        async with sem:
            try:
                d = await _latest(cfg, idx)
            except httpx.HTTPError:
                return None
        if not d:
            return None
        a = d.get("asset", {})
        controls = a.get("controls", [])
        t = _tally(controls)
        return {
            "asset_id": a.get("asset_id"), "asset_uuid": a.get("asset_uuid"),
            "platform": (a.get("component", {}) or {}).get("component", "unknown"),
            "catalog": d.get("metadata", {}).get("catalog_name"),
            "last_scan": d.get("@timestamp"),
            "controls": t["total"], "passed": t["passed"], "failed": t["failed"],
            "not_applicable": t["not_applicable"], "not_run": t["not_run"],
            "compliance_pct": t["compliance_pct"],
            "failed_ids": [c.get("control_id") for c in controls
                           if _bucket(c.get("control_status")) == "failed"],
        }

    all_assets = [a for a in await asyncio.gather(*[one(i) for i in idxs]) if a]
    # Assets whose latest scan evaluated 0 controls are empty/incomplete scans —
    # not "0% compliant". Keep them out of the ranking; just report the count.
    assets = [a for a in all_assets if (a["passed"] + a["failed"] + a["not_applicable"]) > 0]
    skipped_no_data = len(all_assets) - len(assets)

    fleet = {"assets": len(assets), "total": 0, "passed": 0, "failed": 0,
             "not_applicable": 0, "not_run": 0}
    plat: dict[str, dict] = {}
    for a in assets:
        fleet["total"] += a["controls"]
        for k in ("passed", "failed", "not_applicable", "not_run"):
            fleet[k] += a[k]
        p = plat.setdefault(a["platform"], {"platform": a["platform"], "assets": 0,
                                            "controls": 0, "passed": 0, "failed": 0,
                                            "not_applicable": 0})
        p["assets"] += 1
        for k in ("controls", "passed", "failed", "not_applicable"):
            p[k] += a[k]
    fleet["evaluated"] = fleet["passed"] + fleet["failed"] + fleet["not_applicable"]
    fleet["compliance_pct"] = _pct(fleet["passed"], fleet["failed"], fleet["not_applicable"])

    by_platform = []
    for p in plat.values():
        p["compliance_pct"] = _pct(p["passed"], p["failed"], p["not_applicable"])
        by_platform.append(p)
    by_platform.sort(key=lambda x: x["compliance_pct"])

    bands = {"good": 0, "warn": 0, "poor": 0}
    for a in assets:
        c = a["compliance_pct"]
        bands["good" if c >= 90 else "warn" if c >= 70 else "poor"] += 1

    assets.sort(key=lambda a: (a["compliance_pct"], -a["failed"]))

    # Systemic risks: which controls fail on the MOST assets (fix these first).
    fail_counter: Counter = Counter()
    ctrl_platform: dict[str, str] = {}
    rep_by_platform: dict[str, str] = {}
    for a in assets:
        rep_by_platform.setdefault(a["platform"], a["asset_uuid"])
        for cid in a.get("failed_ids", []):
            if not cid:
                continue
            fail_counter[cid] += 1
            ctrl_platform.setdefault(cid, a["platform"])
    top = fail_counter.most_common(20)
    title_map: dict = {}
    for plat in {ctrl_platform[cid] for cid, _ in top}:
        ru = rep_by_platform.get(plat)
        if ru:
            title_map.update(await _titles(cfg, ru, env))
    top_failing = [{"control_id": cid, "assets_failing": n,
                    "platform": ctrl_platform.get(cid), "title": title_map.get(cid, "")}
                   for cid, n in top]
    for a in assets:
        a.pop("failed_ids", None)  # keep the response payload small

    ssps: list[dict] = []
    try:
        d = await _search(cfg, f"grc-ssp-published-{env}",
                          {"size": 100, "query": {"term": {"active": True}}})
        for h in d.get("hits", {}).get("hits", []):
            s = h["_source"].get("ssp", {})
            comps = s.get("components", [])
            ssps.append({"ssp_name": s.get("ssp_name"),
                         "platforms": [c.get("component_name") for c in comps],
                         "total_controls": sum(len(c.get("controls", [])) for c in comps),
                         "assets_targeted": sum(len(c.get("assets", [])) for c in comps)})
    except httpx.HTTPError:
        pass

    out = {"env": env, "generated_at": datetime.now(timezone.utc).isoformat(),
           "fleet": fleet, "by_platform": by_platform, "bands": bands,
           "top_failing_controls": top_failing,
           "asset_count": len(assets), "skipped_no_data": skipped_no_data,
           "assets": assets, "ssp_count": len(ssps), "ssps": ssps}
    if redis is not None:
        try:
            await redis.set(ckey, orjson.dumps(out).decode(), ex=CACHE_TTL_S)
        except Exception:  # noqa: BLE001
            pass
    return out


async def asset_controls(app, asset: str, env: str = "dev", status: str = "failed") -> dict:
    """Controls (id/title/status) for one asset's latest scan (drill-down)."""
    env = _env(env)
    status = (status or "").strip().lower()
    cfg = await _es_config()
    if not cfg:
        return {"error": "No Elasticsearch/GRC connection configured."}
    idx, uuid = await _resolve(cfg, asset, env)
    if not idx:
        return {"error": f"Asset '{asset}' not found in env '{env}'."}
    try:
        d = await _latest(cfg, idx)
    except httpx.HTTPError as exc:
        return {"error": f"ES error: {exc}"}
    if not d:
        return {"error": "No scan results."}
    a = d.get("asset", {})
    titles = await _titles(cfg, uuid or "", env)
    rows = []
    for c in a.get("controls", []):
        if status and status != "all" and _bucket(c.get("control_status")) != status:
            continue
        rows.append({"control_id": c.get("control_id"),
                     "title": titles.get(c.get("control_id"), ""),
                     "status": c.get("control_status")})
    return {"asset_id": a.get("asset_id"), "asset_uuid": uuid, "env": env,
            "platform": (a.get("component", {}) or {}).get("component"),
            "catalog": d.get("metadata", {}).get("catalog_name"),
            "last_scan": d.get("@timestamp"),
            "summary": _tally(a.get("controls", [])),
            "status": status or "all", "controls": rows[:400]}


async def control_detail(app, asset: str, control_id: str, env: str = "dev") -> dict:
    """One control's status + command + evidence (works for both pass and fail)."""
    env = _env(env)
    cfg = await _es_config()
    if not cfg:
        return {"error": "No Elasticsearch/GRC connection configured."}
    idx, uuid = await _resolve(cfg, asset, env)
    if not idx:
        return {"error": f"Asset '{asset}' not found in env '{env}'."}
    try:
        d = await _latest(cfg, idx)
    except httpx.HTTPError as exc:
        return {"error": f"ES error: {exc}"}
    if not d:
        return {"error": "No scan results."}
    found = next((c for c in d.get("asset", {}).get("controls", [])
                  if c.get("control_id") == control_id), None)
    if not found:
        return {"error": f"Control '{control_id}' not found on this asset."}
    titles = await _titles(cfg, uuid or "", env)
    ev = found.get("evidence", {}) or {}
    data = ev.get("data")
    if not isinstance(data, str):
        data = orjson.dumps(data).decode() if data is not None else ""
    return {"asset_id": d.get("asset", {}).get("asset_id"), "env": env,
            "control_id": control_id, "title": titles.get(control_id, ""),
            "status": found.get("control_status"),
            "command_executed": (ev.get("command_executed") or "")[:2000],
            "evidence": data[:4000]}


_SUMMARY_SYS = (
    "You are a compliance officer briefing the CISO / an auditor. From the JSON "
    "compliance posture, write a concise markdown brief with these sections: "
    "**Posture** (1-2 sentences on overall compliance), **Weakest areas** (platforms "
    "+ worst assets by name with their %), **Key risks**, **Recommended actions** "
    "(3-5 prioritized, specific bullets). Use the real numbers. No preamble.\n/no_think"
)


async def stream_compliance_summary(app, env: str = "dev") -> AsyncIterator[str]:
    ov = await compliance_overview(app, env)
    llama = report_service._llama(app)
    if llama is None:
        yield "Inference is not available."
        return
    payload = {
        "env": ov["env"], "fleet": ov.get("fleet", {}), "bands": ov.get("bands", {}),
        "by_platform": ov.get("by_platform", []),
        "worst_assets": [
            {k: a[k] for k in ("asset_id", "platform", "failed", "compliance_pct")}
            for a in ov.get("assets", [])[:12]
        ],
        "top_failing_controls": ov.get("top_failing_controls", [])[:10],
        "published_ssps": len(ov.get("ssps", [])),
    }
    async for kind, delta in llama.stream_chat(
        messages=[{"role": "system", "content": _SUMMARY_SYS},
                  {"role": "user", "content": orjson.dumps(payload).decode()}],
        temperature=0.3, top_p=0.9, max_tokens=750, model="qwen3-8b",
    ):
        if kind == "content":
            yield delta
