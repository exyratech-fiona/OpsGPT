"""Read-only GRC / compliance tools over the ELK evidence store.

The application's data lives in three ES index families (all on the same
cluster; this provider reuses the Elasticsearch connection config):

    SSP input     grc-ssp-published-<env>      what SHOULD be scanned (controls)
    RESULT        <asset_uuid>-<env>           per-scan result; latest doc = current
    RAW evidence  grc-raw-<asset_uuid>-<env>   command output + control_id -> title map

A RESULT doc holds `asset.controls[]` = {control_id, control_status, evidence};
status is one of passed / failed / not applicable(passed) / null(not-run). Each
scan is its own doc, so "current compliance" = the newest doc (sort @timestamp).

These tools do the right nested queries internally and return compact JSON so the
model can answer questions like "how many controls failed for router-01" without
writing ES DSL itself. All operations are GET/_search/_count only (read-only).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import httpx
import orjson

from app.core.logging import get_logger
from app.tools.base import Tool, ToolRegistry

logger = get_logger(__name__)

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_ENV_RE = re.compile(r"^[a-z0-9]{1,20}$", re.I)
_ENVS = ("dev", "sit", "demo", "local", "uat", "preprod", "prod")
# Tool results feed back into the model, whose context is only ~4096 tokens per
# slot (llama.cpp --parallel 2). Keep results small so the answer round fits.
_MAX_OUTPUT = 3200


def _client(cfg: dict) -> httpx.AsyncClient:
    headers, auth = {}, None
    if cfg.get("api_key"):
        headers["Authorization"] = f"ApiKey {cfg['api_key']}"
    elif cfg.get("username"):
        auth = (cfg["username"], cfg.get("password", ""))
    return httpx.AsyncClient(
        base_url=str(cfg.get("url", "")).rstrip("/"),
        headers=headers, auth=auth,
        verify=bool(cfg.get("verify_tls", True)), timeout=25.0,
    )


def _trim(s: str) -> str:
    return s if len(s) <= _MAX_OUTPUT else s[:_MAX_OUTPUT] + "\n… (truncated)"


def _env_of(cfg: dict, a: dict) -> str:
    e = str(a.get("env") or cfg.get("env") or "dev").strip().lower()
    return e if _ENV_RE.match(e) else "dev"


def _bucket(status) -> str:
    s = (status or "").strip().lower()
    if not s:
        return "not_run"
    if s == "failed":
        return "failed"
    if "not applicable" in s:
        return "not_applicable"
    if s == "passed":
        return "passed"
    return "other"


def _tally(controls: list[dict]) -> dict:
    out = {"total": len(controls), "passed": 0, "failed": 0,
           "not_applicable": 0, "not_run": 0, "other": 0}
    for c in controls:
        out[_bucket(c.get("control_status"))] += 1
    evaluated = out["passed"] + out["failed"] + out["not_applicable"]
    compliant = out["passed"] + out["not_applicable"]
    out["evaluated"] = evaluated
    out["compliance_pct"] = round(compliant / evaluated * 100, 1) if evaluated else 0.0
    return out


async def test_connection(cfg: dict) -> tuple[bool, str]:
    try:
        async with _client(cfg) as c:
            r = await c.get("/_cat/indices/grc-ssp-published-*", params={"format": "json", "h": "index,docs.count"})
    except httpx.HTTPError as exc:
        return False, f"connection failed: {exc}"[:300]
    if r.status_code == 401:
        return False, "authentication failed (401)"
    if r.status_code >= 400:
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    try:
        n = len(r.json())
    except ValueError:
        n = 0
    return True, f"Connected — {n} published-SSP index(es) visible."


def build_registry(cfg: dict) -> ToolRegistry:
    async def _get(path: str, params: dict | None = None):
        async with _client(cfg) as c:
            r = await c.get(path, params=params)
        return r

    async def _search(index: str, body: dict) -> dict | None:
        async with _client(cfg) as c:
            r = await c.post(f"/{index}/_search", json=body)
        if r.status_code >= 400:
            raise httpx.HTTPStatusError(r.text[:300], request=r.request, response=r)
        return r.json()

    async def _latest(index: str) -> dict | None:
        data = await _search(index, {"size": 1, "sort": [{"@timestamp": "desc"}],
                                     "query": {"match_all": {}}})
        hits = (data or {}).get("hits", {}).get("hits", [])
        return hits[0]["_source"] if hits else None

    async def _result_indices(env: str) -> list[str]:
        r = await _get(f"/_cat/indices/*-{env}", {"format": "json", "h": "index"})
        if r.status_code >= 400:
            return []
        return sorted(i["index"] for i in r.json()
                      if not i["index"].startswith("grc-") and i["index"].endswith(f"-{env}"))

    async def _resolve(asset: str, env: str) -> tuple[str | None, str | None, str | None]:
        """Return (result_index, asset_uuid, error). asset = uuid or name substring."""
        m = _UUID_RE.search(asset or "")
        if m:
            uuid = m.group(0).lower()
            return f"{uuid}-{env}", uuid, None
        # name search across all result indices for this env (exclude raw/ssp)
        try:
            data = await _search(
                f"*-{env},-grc-*",
                {"size": 3,
                 "query": {"query_string": {
                     "query": f"asset.asset_id:*{asset}* OR asset.hostname:*{asset}*",
                     "analyze_wildcard": True}},
                 "_source": ["asset.asset_uuid", "asset.asset_id"]},
            )
        except httpx.HTTPError:
            data = None
        hits = (data or {}).get("hits", {}).get("hits", [])
        if hits:
            idx = hits[0]["_index"]
            uuid = hits[0]["_source"].get("asset", {}).get("asset_uuid")
            return idx, uuid, None
        return None, None, f"asset '{asset}' not found in env '{env}'. Use grc_list_assets to see valid asset names."

    # ---- tools -------------------------------------------------------------
    async def list_ssps(a: dict) -> str:
        raw_env = str(a.get("env") or cfg.get("env") or "").strip().lower()
        # only scope to a real environment; "all"/""/unknown -> every environment
        scoped = raw_env in _ENVS
        idx = f"grc-ssp-published-{raw_env}" if scoped else "grc-ssp-published-*"
        try:
            data = await _search(idx, {"size": 200, "query": {"term": {"active": True}}})
        except httpx.HTTPError as exc:
            return f"GRC error: {exc}"
        out = []
        for h in (data or {}).get("hits", {}).get("hits", []):
            s = h["_source"].get("ssp", {})
            comps = s.get("components", [])
            pub = s.get("ssp_published_at")
            pub_iso = ""
            try:
                if pub:
                    pub_iso = datetime.fromtimestamp(float(pub), tz=timezone.utc).isoformat()
            except (TypeError, ValueError, OSError):
                pub_iso = ""
            out.append({
                "ssp_name": s.get("ssp_name"),
                "env": h.get("_index", "").replace("grc-ssp-published-", ""),
                "published_at": pub_iso,
                "platforms": [c.get("component_name") for c in comps],
                "total_controls": sum(len(c.get("controls", [])) for c in comps),
            })
        out.sort(key=lambda x: x.get("published_at") or "", reverse=True)
        total = len(out)
        return _trim(orjson.dumps({
            "scope": raw_env or "all environments",
            "count": total,
            "note": "sorted newest-first; the first item is the LATEST SSP",
            "published_ssps": out[:15],
        }).decode())

    async def list_assets(a: dict) -> str:
        env = _env_of(cfg, a)
        platform = str(a.get("platform") or "").strip().lower()
        idxs = await _result_indices(env)
        rows = []
        for idx in idxs[:80]:
            try:
                d = await _latest(idx)
            except httpx.HTTPError:
                continue
            if not d:
                continue
            asset = d.get("asset", {})
            plat = (asset.get("component", {}) or {}).get("component", "")
            if platform and platform not in str(plat).lower():
                continue
            t = _tally(asset.get("controls", []))
            rows.append({
                "asset_id": asset.get("asset_id"), "platform": plat,
                "controls": t["total"], "passed": t["passed"], "failed": t["failed"],
                "compliance_pct": t["compliance_pct"],
            })
        rows.sort(key=lambda r: r["compliance_pct"])
        return _trim(orjson.dumps({"env": env, "asset_count": len(rows),
                                   "note": "worst-compliance first; showing up to 20",
                                   "assets": rows[:20]}).decode())

    async def compliance_summary(a: dict) -> str:
        env = _env_of(cfg, a)
        asset = str(a.get("asset") or "").strip()
        if asset:
            idx, uuid, err = await _resolve(asset, env)
            if err:
                return err
            try:
                d = await _latest(idx)
            except httpx.HTTPError as exc:
                return f"GRC error: {exc}"
            if not d:
                return f"No scan results for asset '{asset}' in env '{env}'."
            asset_obj = d.get("asset", {})
            t = _tally(asset_obj.get("controls", []))
            return _trim(orjson.dumps({
                "asset_id": asset_obj.get("asset_id"), "asset_uuid": uuid, "env": env,
                "platform": (asset_obj.get("component", {}) or {}).get("component"),
                "catalog": d.get("metadata", {}).get("catalog_name"),
                "last_scan": d.get("@timestamp"), **t,
            }).decode())
        # fleet-wide rollup
        idxs = await _result_indices(env)
        agg = {"assets": 0, "total": 0, "passed": 0, "failed": 0, "not_applicable": 0, "not_run": 0}
        by_platform: dict[str, dict] = {}
        for idx in idxs[:80]:
            try:
                d = await _latest(idx)
            except httpx.HTTPError:
                continue
            if not d:
                continue
            asset_obj = d.get("asset", {})
            t = _tally(asset_obj.get("controls", []))
            plat = (asset_obj.get("component", {}) or {}).get("component", "unknown")
            agg["assets"] += 1
            for k in ("total", "passed", "failed", "not_applicable", "not_run"):
                agg[k] += t[k]
            p = by_platform.setdefault(plat, {"assets": 0, "failed": 0, "passed": 0, "total": 0})
            p["assets"] += 1
            p["failed"] += t["failed"]; p["passed"] += t["passed"]; p["total"] += t["total"]
        ev = agg["passed"] + agg["failed"] + agg["not_applicable"]
        agg["compliance_pct"] = round((agg["passed"] + agg["not_applicable"]) / ev * 100, 1) if ev else 0.0
        return _trim(orjson.dumps({"env": env, "fleet": agg, "by_platform": by_platform}).decode())

    async def _control_titles(uuid: str, env: str) -> dict:
        """control_id -> human title, from the raw index's control_id_map."""
        try:
            d = await _latest(f"grc-raw-{uuid}-{env}")
        except httpx.HTTPError:
            return {}
        return ((d or {}).get("raw_data", {}) or {}).get("control_id_map", {}) or {}

    async def list_controls(a: dict) -> str:
        env = _env_of(cfg, a)
        asset = str(a.get("asset") or "").strip()
        if not asset:
            return "Provide 'asset' (name or uuid). Use grc_list_assets to see options."
        want = str(a.get("status") or "").strip().lower()  # failed|passed|not_applicable|""
        try:
            limit = max(1, min(int(a.get("limit", 25)), 40))
        except (TypeError, ValueError):
            limit = 25
        idx, uuid, err = await _resolve(asset, env)
        if err:
            return err
        try:
            d = await _latest(idx)
        except httpx.HTTPError as exc:
            return f"GRC error: {exc}"
        if not d:
            return f"No scan results for asset '{asset}'."
        titles = await _control_titles(uuid, env)
        rows = []
        for c in d.get("asset", {}).get("controls", []):
            if want and _bucket(c.get("control_status")) != want:
                continue
            rows.append({"control_id": c.get("control_id"),
                         "title": titles.get(c.get("control_id"), ""),
                         "status": c.get("control_status")})
        t = _tally(d.get("asset", {}).get("controls", []))
        rows = rows[:limit]
        return _trim(orjson.dumps({
            "asset_id": d.get("asset", {}).get("asset_id"), "env": env,
            "filter_status": want or "all", "summary": t,
            "returned": len(rows), "controls": rows}).decode())

    async def control_detail(a: dict) -> str:
        env = _env_of(cfg, a)
        asset = str(a.get("asset") or "").strip()
        control_id = str(a.get("control_id") or "").strip()
        if not asset or not control_id:
            return "Provide both 'asset' and 'control_id'."
        idx, uuid, err = await _resolve(asset, env)
        if err:
            return err
        try:
            d = await _latest(idx)
        except httpx.HTTPError as exc:
            return f"GRC error: {exc}"
        if not d:
            return f"No scan results for asset '{asset}'."
        found = next((c for c in d.get("asset", {}).get("controls", [])
                      if c.get("control_id") == control_id), None)
        if not found:
            return f"Control '{control_id}' not found on asset '{asset}'."
        titles = await _control_titles(uuid, env)
        ev = found.get("evidence", {}) or {}
        return _trim(orjson.dumps({
            "asset_id": d.get("asset", {}).get("asset_id"), "env": env,
            "control_id": control_id, "title": titles.get(control_id, ""),
            "status": found.get("control_status"),
            "command_executed": (ev.get("command_executed") or "")[:1500],
            "evidence": (ev.get("data") or "")[:2500],
        }).decode())

    async def search_controls(a: dict) -> str:
        env = _env_of(cfg, a)
        kw = str(a.get("keyword") or "").strip().lower()
        if not kw:
            return "Provide a 'keyword' to search control titles."
        asset = str(a.get("asset") or "").strip()
        # need a control_id_map: use the given asset's raw, else the first asset of env
        if asset:
            _idx, uuid, err = await _resolve(asset, env)
            if err:
                return err
        else:
            idxs = await _result_indices(env)
            if not idxs:
                return f"No assets in env '{env}'."
            m = _UUID_RE.search(idxs[0])
            uuid = m.group(0) if m else None
        titles = await _control_titles(uuid or "", env)
        matches = [{"control_id": cid, "title": t}
                   for cid, t in titles.items() if kw in str(t).lower()]
        return _trim(orjson.dumps({"env": env, "keyword": kw,
                                   "match_count": len(matches), "matches": matches[:30]}).decode())

    reg = ToolRegistry()
    reg.register(Tool(
        "grc_list_ssps",
        "List published SSPs (System Security Plans) NEWEST-FIRST with published date, "
        "platforms, and control counts. Use for 'the latest SSP', 'which SSPs exist', "
        "'how many controls in <SSP>'. Omit env to search ALL environments (the first "
        "result is the most recently published SSP).",
        {"type": "object", "properties": {"env": {"type": "string", "description": "dev|sit|demo|local|uat; omit for all environments"}}},
        list_ssps))
    reg.register(Tool(
        "grc_list_assets",
        "List scanned assets/servers with their platform, last scan, and pass/fail control counts + compliance %. Optional platform filter (Linux|OCI|Kubernetes|AWS|Windows|MySQL|Postgres).",
        {"type": "object", "properties": {"env": {"type": "string"}, "platform": {"type": "string"}}},
        list_assets))
    reg.register(Tool(
        "grc_compliance_summary",
        "Compliance summary. With 'asset' (name or uuid): that asset's latest pass/fail/na counts + compliance %. Without: fleet-wide rollup for the env by platform.",
        {"type": "object", "properties": {"asset": {"type": "string"}, "env": {"type": "string"}}},
        compliance_summary))
    reg.register(Tool(
        "grc_list_controls",
        "List an asset's controls (id + title + status) from its latest scan. Optional status filter: failed|passed|not_applicable.",
        {"type": "object", "properties": {"asset": {"type": "string"}, "status": {"type": "string"},
                                          "env": {"type": "string"}, "limit": {"type": "integer"}},
         "required": ["asset"]},
        list_controls))
    reg.register(Tool(
        "grc_control_detail",
        "Full detail for one control on one asset: title, pass/fail status, the exact command executed and the evidence/output (why it passed or failed).",
        {"type": "object", "properties": {"asset": {"type": "string"}, "control_id": {"type": "string"},
                                          "env": {"type": "string"}},
         "required": ["asset", "control_id"]},
        control_detail))
    reg.register(Tool(
        "grc_search_controls",
        "Find controls whose title matches a keyword (e.g. 'ssh', 'firewall', 'password'). Optional asset/platform to pick the catalog.",
        {"type": "object", "properties": {"keyword": {"type": "string"}, "asset": {"type": "string"},
                                          "env": {"type": "string"}},
         "required": ["keyword"]},
        search_controls))
    return reg
