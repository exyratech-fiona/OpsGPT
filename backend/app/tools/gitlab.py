"""Read-only GitLab tools (CI/CD), parameterised by config: {url, token, verify_tls}.

Uses the GitLab REST API v4 with a PRIVATE-TOKEN (read_api scope is enough).
Only GET requests — no writes/triggers/cancels.

Project resolution is robust: the `project` argument may be a numeric id, a full
group/subgroup/project path, OR a pasted GitLab URL. When a path can't be opened
directly the tool searches by name and, if there is a single/exact match, uses it;
otherwise it returns the candidate list so the model (or user) can pick the id.
"""

from __future__ import annotations

import asyncio
import re
from urllib.parse import quote, urlsplit

import httpx
import orjson

from app.core.logging import get_logger
from app.tools.base import Tool, ToolRegistry

logger = get_logger(__name__)

_ID_RE = re.compile(r"^[0-9]+$")
_PATH_RE = re.compile(r"^[A-Za-z0-9_.\-/]{1,255}$")
_MAX_OUTPUT = 6000


def _client(cfg: dict) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=str(cfg.get("url", "")).rstrip("/") + "/api/v4",
        headers={"PRIVATE-TOKEN": str(cfg.get("token", ""))},
        verify=bool(cfg.get("verify_tls", True)),
        timeout=25.0,
    )


def _trim(t: str) -> str:
    return t[:_MAX_OUTPUT] + "\n… (truncated)" if len(t) > _MAX_OUTPUT else t


def _parse_project(value: str) -> str:
    """Normalise a project reference: numeric id, group/path, or a pasted URL.

    Examples:
      "116"                                                  -> "116"
      "DOL/code8-frontend/celcomdigi_exorafe"                -> same
      "https://gl.host/DOL/code8-frontend/x/-/pipelines"     -> "DOL/code8-frontend/x"
    """
    value = str(value or "").strip()
    if not value:
        return ""
    # Full URL (with scheme) or host-leading path that includes the UI separator.
    if "://" in value:
        path = urlsplit(value).path
    elif "/-/" in value and " " not in value and "." in value.split("/", 1)[0]:
        path = urlsplit("https://" + value).path
    else:
        path = value
    path = path.strip("/")
    # Strip GitLab's UI separator and everything after it (/-/pipelines, /-/tree/…).
    if "/-/" in path:
        path = path.split("/-/", 1)[0].strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return path


def _compact(data, fields: list[str]) -> str:
    """Reduce a list of objects to just the interesting fields."""
    if isinstance(data, list):
        rows = [{k: d.get(k) for k in fields if k in d} for d in data if isinstance(d, dict)]
        return _trim(orjson.dumps(rows).decode())
    return _trim(orjson.dumps(data).decode())


def _as_refs(value) -> list[str]:
    """Normalise a projects value (list, or newline/comma string) to a list."""
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [p.strip() for p in re.split(r"[\n,]", value) if p.strip()]
    return []


def _configured_projects(cfg: dict) -> list[str]:
    """All project refs the connection knows: default first, then the watchlist."""
    refs: list[str] = []
    dp = str(cfg.get("default_project") or "").strip()
    if dp:
        refs.append(dp)
    for r in _as_refs(cfg.get("projects")) + _as_refs(cfg.get("favorites")):
        if r not in refs:
            refs.append(r)
    return refs


async def test_connection(cfg: dict) -> tuple[bool, str]:
    try:
        async with _client(cfg) as c:
            r = await c.get("/version")
    except httpx.HTTPError as exc:
        return False, f"connection failed: {exc}"[:300]
    if r.status_code in (401, 403):
        return False, "authentication failed (check token / read_api scope)"
    if r.status_code >= 400:
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    try:
        return True, f"Connected — GitLab {r.json().get('version')}."
    except ValueError:
        return True, "Connected."


def build_registry(cfg: dict) -> ToolRegistry:
    async def get(path: str, params: dict | None = None) -> tuple[int, str]:
        try:
            async with _client(cfg) as c:
                r = await c.get(path, params=params)
        except httpx.HTTPError as exc:
            return 0, f"GitLab error: {exc}"
        return r.status_code, r.text

    async def _resolve(project_raw: str) -> tuple[str | None, str | None, list | None]:
        """Resolve a project reference to a numeric id.

        Returns (id, error, candidates). On success id is set; on ambiguity
        candidates is a list of {id, path}; otherwise error explains the miss.
        """
        p = _parse_project(project_raw)
        if not p:
            return None, "missing 'project'", None
        if _ID_RE.match(p):
            return p, None, None
        # 1) try the path verbatim (handles nested group/subgroup/project)
        if _PATH_RE.match(p):
            code, body = await get(f"/projects/{quote(p, safe='')}")
            if code == 200:
                try:
                    return str(orjson.loads(body)["id"]), None, None
                except (orjson.JSONDecodeError, KeyError, TypeError):
                    pass
        # 2) search by the last path segment (the project's own name)
        name = p.rstrip("/").split("/")[-1]
        code, body = await get(
            "/projects", {"search": name, "per_page": 30, "simple": "true", "membership": "true"}
        )
        rows: list = []
        if code == 200:
            try:
                rows = orjson.loads(body)
            except orjson.JSONDecodeError:
                rows = []
        # exact full-path match wins outright
        exact = [r for r in rows if str(r.get("path_with_namespace", "")).lower() == p.lower()]
        if len(exact) == 1:
            return str(exact[0]["id"]), None, None
        if len(rows) == 1:
            return str(rows[0]["id"]), None, None
        if rows:
            cands = [{"id": r.get("id"), "path": r.get("path_with_namespace")} for r in rows[:15]]
            return None, "ambiguous", cands
        return None, f"no project matching '{p}'", None

    async def _project_id(project_raw: str) -> tuple[str | None, str | None]:
        """Convenience: resolve to id or a ready-to-return user message.

        When no project is given, fall back to the connection's default project
        (default_project, or the first configured project).
        """
        raw = str(project_raw or "").strip()
        if not raw:
            configured = _configured_projects(cfg)
            raw = configured[0] if configured else ""
        pid, err, cands = await _resolve(raw)
        if pid:
            return pid, None
        if cands:
            return None, (
                "Multiple projects match — re-run with the numeric id of the right one:\n"
                + _compact(cands, ["id", "path"])
            )
        return None, (
            f"Error: {err}. Call gl_list_projects with a search term (e.g. the project "
            "name) to find its numeric id, then use that id."
        )

    async def list_projects(a: dict) -> str:
        params = {"membership": "true", "per_page": 30, "order_by": "last_activity_at", "simple": "true"}
        if a.get("search"):
            params["search"] = str(a["search"])[:100]
        code, body = await get("/projects", params)
        if code >= 400 or code == 0:
            return f"GitLab {code}: {body[:300]}"
        try:
            return _compact(orjson.loads(body), ["id", "path_with_namespace", "default_branch", "web_url"])
        except orjson.JSONDecodeError:
            return _trim(body)

    async def list_pipelines(a: dict) -> str:
        pid, msg = await _project_id(a.get("project", ""))
        if msg:
            return msg
        params = {"per_page": 15}
        if a.get("ref"):
            params["ref"] = str(a["ref"])[:200]
        if a.get("status"):
            params["status"] = str(a["status"])[:20]
        code, body = await get(f"/projects/{pid}/pipelines", params)
        if code >= 400 or code == 0:
            return f"GitLab {code}: {body[:300]}"
        try:
            return _compact(orjson.loads(body), ["id", "status", "ref", "sha", "source", "created_at", "web_url"])
        except orjson.JSONDecodeError:
            return _trim(body)

    async def get_pipeline(a: dict) -> str:
        pid, msg = await _project_id(a.get("project", ""))
        if msg:
            return msg
        plid = str(a.get("pipeline_id", ""))
        if not _ID_RE.match(plid):
            return "Error: invalid/missing 'pipeline_id' (the numeric pipeline id)."
        code, body = await get(f"/projects/{pid}/pipelines/{plid}")
        if code >= 400 or code == 0:
            return f"GitLab {code}: {body[:300]}"
        try:
            d = orjson.loads(body)
            return _compact(d, ["id", "status", "ref", "sha", "source", "duration",
                                "created_at", "updated_at", "web_url"])
        except orjson.JSONDecodeError:
            return _trim(body)

    async def pipeline_jobs(a: dict) -> str:
        pid, msg = await _project_id(a.get("project", ""))
        if msg:
            return msg
        plid = str(a.get("pipeline_id", ""))
        if not _ID_RE.match(plid):
            return "Error: invalid/missing 'pipeline_id'."
        code, body = await get(f"/projects/{pid}/pipelines/{plid}/jobs", {"per_page": 50})
        if code >= 400 or code == 0:
            return f"GitLab {code}: {body[:300]}"
        try:
            return _compact(orjson.loads(body), ["id", "name", "stage", "status", "duration"])
        except orjson.JSONDecodeError:
            return _trim(body)

    async def job_log(a: dict) -> str:
        pid, msg = await _project_id(a.get("project", ""))
        if msg:
            return msg
        jid = str(a.get("job_id", ""))
        if not _ID_RE.match(jid):
            return "Error: invalid/missing 'job_id'."
        code, body = await get(f"/projects/{pid}/jobs/{jid}/trace")
        if code >= 400 or code == 0:
            return f"GitLab {code}: {body[:300]}"
        # logs can be huge — return the tail
        return _trim(body[-_MAX_OUTPUT:])

    async def latest_pipelines(a: dict) -> str:
        """Latest pipeline for each project — the configured watchlist by default."""
        refs = _as_refs(a.get("projects")) or _configured_projects(cfg)
        if not refs:
            return ("No projects are configured for this GitLab connection. Add projects "
                    "in the Tool Connections panel, or pass 'projects' explicitly.")

        async def one(ref: str) -> dict:
            pid, msg = await _project_id(ref)
            if not pid:
                return {"project": ref, "error": (msg or "")[:120]}
            code, body = await get(f"/projects/{pid}/pipelines", {"per_page": 1})
            if code >= 400 or code == 0:
                return {"project": ref, "error": f"HTTP {code}"}
            try:
                arr = orjson.loads(body)
            except orjson.JSONDecodeError:
                arr = []
            if not arr:
                return {"project": ref, "status": "no pipelines yet"}
            p = arr[0]
            return {
                "project": ref,
                "pipeline_id": p.get("id"),
                "status": p.get("status"),
                "ref": p.get("ref"),
                "created_at": p.get("created_at"),
                "web_url": p.get("web_url"),
            }

        results = await asyncio.gather(*[one(r) for r in refs[:20]])
        return _trim(orjson.dumps(list(results)).decode())

    async def list_mrs(a: dict) -> str:
        pid, msg = await _project_id(a.get("project", ""))
        if msg:
            return msg
        state = a.get("state", "opened")
        code, body = await get(f"/projects/{pid}/merge_requests", {"state": state, "per_page": 20})
        if code >= 400 or code == 0:
            return f"GitLab {code}: {body[:300]}"
        try:
            return _compact(orjson.loads(body), ["iid", "title", "state", "source_branch", "target_branch", "author", "web_url"])
        except orjson.JSONDecodeError:
            return _trim(body)

    _proj_desc = ("numeric id, full path (group/subgroup/project), or a pasted GitLab "
                  "URL — the tool resolves it, searching by name if needed. Omit to use "
                  "the connection's default project.")

    reg = ToolRegistry()
    reg.register(Tool("gl_list_projects",
                      "Find GitLab projects by search term and get each one's numeric id + full "
                      "path. ALWAYS use this first when the user names a project but you don't "
                      "have its exact path/id — projects are often nested several groups deep.",
                      {"type": "object", "properties": {
                          "search": {"type": "string", "description": "project name or keyword to search for"}}},
                      list_projects))
    reg.register(Tool("gl_latest_pipelines",
                      "Report the single most-recent pipeline (status/ref/url) for EACH configured "
                      "project at once. Use this when the user asks about 'the latest pipeline(s)', "
                      "overall CI status, or doesn't name a specific project — it covers the whole "
                      "watchlist configured for this connection.",
                      {"type": "object", "properties": {
                          "projects": {"type": "array", "items": {"type": "string"},
                                       "description": "optional explicit project refs; omit to use the configured watchlist"}}},
                      latest_pipelines))
    reg.register(Tool("gl_list_pipelines",
                      "List recent CI/CD pipelines for ONE project (newest first); optional ref/status filter.",
                      {"type": "object", "properties": {
                          "project": {"type": "string", "description": _proj_desc},
                          "ref": {"type": "string", "description": "branch/tag filter"},
                          "status": {"type": "string", "description": "e.g. failed, success, running"}}},
                      list_pipelines))
    reg.register(Tool("gl_pipeline",
                      "Get a single pipeline's status/ref/sha/duration by its pipeline id.",
                      {"type": "object", "properties": {
                          "project": {"type": "string", "description": _proj_desc},
                          "pipeline_id": {"type": "string", "description": "the numeric pipeline id"}},
                       "required": ["pipeline_id"]}, get_pipeline))
    reg.register(Tool("gl_pipeline_jobs",
                      "List jobs (name/stage/status/duration) of a pipeline.",
                      {"type": "object", "properties": {
                          "project": {"type": "string", "description": _proj_desc},
                          "pipeline_id": {"type": "string"}},
                       "required": ["pipeline_id"]}, pipeline_jobs))
    reg.register(Tool("gl_job_log",
                      "Fetch the trailing log/trace of a CI job (to diagnose failures).",
                      {"type": "object", "properties": {
                          "project": {"type": "string", "description": _proj_desc},
                          "job_id": {"type": "string"}},
                       "required": ["job_id"]}, job_log))
    reg.register(Tool("gl_list_merge_requests",
                      "List merge requests for a project (state: opened/merged/closed).",
                      {"type": "object", "properties": {
                          "project": {"type": "string", "description": _proj_desc},
                          "state": {"type": "string"}}},
                      list_mrs))
    return reg
