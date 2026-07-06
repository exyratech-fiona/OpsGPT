"""Delivery & Reliability reporting.

Scans GitLab (a whole group, incl. subgroups) for failed pipelines and
Kubernetes for failing pods/jobs, caches the result in Redis, refreshes it in
the background, and produces LLM root-cause analysis for a single failure.

Config is read from the existing MCP providers (the enabled GitLab + Kubernetes
connections), so there is a single source of truth. The GitLab group to scan is
`report_group` on the GitLab connection config (defaults to DOL).
"""

from __future__ import annotations

import asyncio
import hashlib
import html as _html
import re
import smtplib
import statistics
from collections import Counter, defaultdict
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import quote

import httpx
import orjson
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import AsyncSessionLocal
from app.db.models import McpServer
from app.services import mcp_service
from app.tools import kubernetes as k8s_provider

logger = get_logger(__name__)
settings = get_settings()

CACHE_KEY = "report:failures"
DELIVERY_CACHE_KEY = "report:delivery"
DEFAULT_GROUP = "DOL"
DEFAULT_WINDOW_HOURS = 48
DEFAULT_WINDOW_DAYS = 7
SCAN_INTERVAL_S = 300
DELIVERY_INTERVAL_S = 1800
GL_CONCURRENCY = 10
TZ_OFFSET_HOURS = 8  # day-bucketing timezone (Malaysia / UTC+8)
MAX_CLASSIFY = 250  # cap LLM bug/feature classification per scan

# Environment buckets, parsed from the GitLab environment name. Order matters:
# check more specific / higher envs first so "PROD" wins over a stray "dev".
ENV_PATTERNS = [
    ("PROD", re.compile(r"prod|production|\bprd\b", re.I)),
    ("UAT", re.compile(r"\buat\b", re.I)),
    ("PREPROD", re.compile(r"pre-?prod|staging|\bstg\b|\bstage\b", re.I)),
    ("SIT", re.compile(r"\bsit\b", re.I)),
    ("DEMO", re.compile(r"\bdemo\b", re.I)),
    ("DEV", re.compile(r"\bdev\b|develop", re.I)),
]
ENV_ORDER = ["DEV", "SIT", "DEMO", "UAT", "PREPROD", "PROD", "OTHER"]

# Detect deploys from JOB NAMES too (e.g. "deploy-to-sit", "deploy_dev", "Deploy to DEMO"),
# since many projects deploy via plain jobs without a GitLab `environment:` (which the
# Deployments API needs). Deduped against the Deployments API by job id.
DEPLOY_JOB_RE = re.compile(
    r"deploy[-_ ]*(?:to[-_ ]*)?(dev|sit|demo|uat|pre-?prod|staging|stg|prod(?:uction)?)\b",
    re.I,
)


def _env_bucket(name: str | None) -> str:
    n = name or ""
    for label, pat in ENV_PATTERNS:
        if pat.search(n):
            return label
    return "OTHER"


def _user_name(u) -> str:
    if not isinstance(u, dict):
        return ""
    return u.get("name") or u.get("username") or ""


# Shared/role GitLab seats (and CI bots): when a commit's author_name is one of
# these, fall back to the author EMAIL's local-part to find the real person.
GENERIC_AUTHORS = {
    "frontenduser", "backenduser", "maintainer", "support", "developer", "dev",
    "gitlab", "gitlab-ci", "root", "administrator", "admin", "ci", "bot", "jenkins",
}


def _commit_author(commit) -> str:
    """The real developer behind a commit (from their local git config), with a
    fallback to the email local-part when the name is a shared/role account."""
    if not isinstance(commit, dict):
        return ""
    name = (commit.get("author_name") or "").strip()
    email = (commit.get("author_email") or "").strip()
    if name and name.lower() not in GENERIC_AUTHORS:
        return name
    if email:
        return email.split("@")[0]  # e.g. ajith.b@devopslabs.tech -> "ajith.b"
    return name


def _commit_identity(commit, fallback_user=None, is_merge=False) -> tuple[str, str]:
    """Return (display, key) for a commit. key is the unique grouping identity.

    Normally key = email (unique per person), display = the real name.
    BUT a MERGE commit made via a SHARED seat (e.g. 'maintainer', whose email may
    be a real person's) is credited to the SEAT — otherwise the seat's email owner
    gets falsely credited for every merge anyone performs through that account."""
    name = email = ""
    if isinstance(commit, dict):
        name = (commit.get("author_name") or "").strip()
        email = (commit.get("author_email") or "").strip().lower()
    generic = bool(name) and name.lower() in GENERIC_AUTHORS

    if is_merge and generic:
        return name, name.lower()                 # credit the seat (e.g. "maintainer")
    if name and not generic:
        return name, email or name.lower()         # real personal commit
    if email:
        return email.split("@")[0], email          # generic name but personal email -> the person
    if isinstance(fallback_user, dict):
        fn = fallback_user.get("name") or fallback_user.get("username") or ""
        return fn, fn.lower()
    return "", ""


def _label_people(count: Counter, names: dict, top: int = 1000) -> list[dict]:
    """Build a leaderboard from email-keyed counts, disambiguating only when two
    distinct people share the same display name (append their email handle)."""
    disp: dict[str, str] = {}
    for key in count:
        nm = names.get(key) or ""
        disp[key] = nm or (key.split("@")[0] if "@" in key else key)
    groups: dict[str, list[str]] = defaultdict(list)
    for k, v in disp.items():
        groups[v].append(k)
    for label, keys in groups.items():
        if len(keys) > 1:  # same name, different people -> add the email handle
            for k in keys:
                disp[k] = f"{label} ({k.split('@')[0] if '@' in k else k})"
    return [{"user": disp[k], "deploys": c} for k, c in count.most_common(top)]


REAL_ENVS = {"SIT", "DEMO", "UAT", "PREPROD", "PROD"}


def _person_rows(person_env: dict, person_name: dict, person_promo: dict) -> list[dict]:
    """Per-developer distinct-commit counts split DEV vs real environments,
    ranked by meaningful (real-env) promotions. Disambiguates same-name people."""
    rows: list[dict] = []
    for key, envs in person_env.items():
        all_sha: set = set()
        real_sha: set = set()
        for e, shas in envs.items():
            all_sha |= shas
            if e in REAL_ENVS:
                real_sha |= shas
        rows.append({
            "key": key,
            "user": person_name.get(key) or key.split("@")[0],
            "total": len(all_sha),
            "dev": len(envs.get("DEV", set())),
            "real": len(real_sha),
            "by_env": {e: len(s) for e, s in sorted(envs.items())},
            "promotions": person_promo.get(key, [])[:50],
        })
    groups: dict = defaultdict(list)
    for r in rows:
        groups[r["user"]].append(r["key"])
    for r in rows:
        if len(groups[r["user"]]) > 1 and "@" in r["key"]:
            r["user"] = f'{r["user"]} ({r["key"].split("@")[0]})'
    rows.sort(key=lambda r: (-r["real"], -r["total"]))
    for r in rows:
        r.pop("key", None)
    return rows


def _parse_dt(iso: str | None):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def _local_date(iso: str | None) -> str | None:
    dt = _parse_dt(iso)
    return (dt + timedelta(hours=TZ_OFFSET_HOURS)).strftime("%Y-%m-%d") if dt else None

# Container waiting/terminated reasons we treat as "failing".
BAD_REASONS = {
    "CrashLoopBackOff", "Error", "ImagePullBackOff", "ErrImagePull",
    "CreateContainerError", "CreateContainerConfigError", "RunContainerError",
    "OOMKilled", "Evicted", "ContainerStatusUnknown", "DeadlineExceeded",
    "InvalidImageName", "CrashLoop",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Provider config loading (from the MCP servers table)
# --------------------------------------------------------------------------- #
async def _provider_config(ptype: str) -> dict | None:
    async with AsyncSessionLocal() as db:
        s = (await db.execute(
            select(McpServer).where(
                McpServer.provider_type == ptype, McpServer.enabled.is_(True)
            )
        )).scalars().first()
    return (s.config or {}) if s else None


async def _kube_path() -> str | None:
    async with AsyncSessionLocal() as db:
        s = (await db.execute(
            select(McpServer).where(
                McpServer.provider_type == "kubernetes", McpServer.enabled.is_(True)
            )
        )).scalars().first()
    if not s:
        return None
    return mcp_service._write_kubeconfig(str(s.id), (s.config or {}).get("kubeconfig", ""))


def _gl_client(cfg: dict) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=str(cfg.get("url", "")).rstrip("/") + "/api/v4",
        headers={"PRIVATE-TOKEN": str(cfg.get("token", ""))},
        verify=bool(cfg.get("verify_tls", True)),
        timeout=25.0,
    )


# --------------------------------------------------------------------------- #
# GitLab failure scan
# --------------------------------------------------------------------------- #
async def _group_projects(client: httpx.AsyncClient, group: str) -> list[dict]:
    projects: list[dict] = []
    page = 1
    while page <= 15:
        r = await client.get(
            f"/groups/{quote(group, safe='')}/projects",
            params={"include_subgroups": "true", "per_page": 100, "page": page,
                    "simple": "true", "archived": "false", "with_shared": "false"},
        )
        if r.status_code >= 400:
            break
        batch = r.json()
        if not batch:
            break
        projects.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return projects


async def scan_gitlab_failures(cfg: dict, group: str, since_iso: str) -> dict:
    async with _gl_client(cfg) as client:
        projects = await _group_projects(client, group)
        sem = asyncio.Semaphore(GL_CONCURRENCY)

        async def one(p: dict) -> list[dict]:
            async with sem:
                try:
                    r = await client.get(
                        f"/projects/{p['id']}/pipelines",
                        params={"status": "failed", "updated_after": since_iso,
                                "per_page": 10, "order_by": "updated_at"},
                    )
                    if r.status_code >= 400:
                        return []
                    return [
                        {
                            "project_id": p["id"],
                            "project": p.get("path_with_namespace"),
                            "pipeline_id": pl.get("id"),
                            "ref": pl.get("ref"),
                            "sha": (pl.get("sha") or "")[:10],
                            "web_url": pl.get("web_url"),
                            "created_at": pl.get("created_at"),
                        }
                        for pl in r.json()
                    ]
                except (httpx.HTTPError, KeyError, ValueError):
                    return []

        nested = await asyncio.gather(*[one(p) for p in projects])
        failed = [item for sub in nested for item in sub]
        failed.sort(key=lambda x: x.get("created_at") or "", reverse=True)

        # Enrich the most recent failures with the real commit AUTHOR (the dev's
        # local git identity), not the shared GitLab seat that triggered the run.
        async def enrich(pl: dict) -> None:
            sha = pl.get("sha")
            if not sha:
                return
            async with sem:
                try:
                    r = await client.get(f"/projects/{pl['project_id']}/repository/commits/{sha}")
                    if r.status_code < 400:
                        cm = r.json()
                        t = cm.get("title") or ""
                        if t.startswith("Merge branch '") and "' into '" in t:
                            pl["user"] = "(merge / integration)"
                            pl["user_email"] = ""
                        else:
                            display, key = _commit_identity(cm, None, t.startswith("Merge "))
                            pl["user"] = display
                            pl["user_email"] = key
                except httpx.HTTPError:
                    pass

        await asyncio.gather(*[enrich(pl) for pl in failed[:80]])

    # Disambiguate failures where two DIFFERENT people share a display name.
    name_emails: dict[str, set] = defaultdict(set)
    for pl in failed:
        if pl.get("user") and pl.get("user_email"):
            name_emails[pl["user"]].add(pl["user_email"])
    for pl in failed:
        em = pl.get("user_email")
        if em and len(name_emails.get(pl.get("user", ""), set())) > 1:
            pl["user"] = f"{pl['user']} ({em.split('@')[0]})"
    return {"projects_scanned": len(projects), "failed_pipelines": failed}


# --------------------------------------------------------------------------- #
# Kubernetes failure scan
# --------------------------------------------------------------------------- #
async def _kubectl_raw(kubeconfig: str, *args: str, timeout: float = 45.0) -> tuple[str | None, str | None]:
    """Run kubectl and return (stdout, error) WITHOUT truncation (for -o json)."""
    cmd = ["kubectl", "--kubeconfig", kubeconfig, *args]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        return None, "kubectl timed out"
    except FileNotFoundError:
        return None, "kubectl not available"
    if proc.returncode != 0:
        return None, err.decode("utf-8", "replace").strip()[:300]
    return out.decode("utf-8", "replace"), None


async def scan_k8s_failures(kubeconfig: str) -> dict:
    raw, err = await _kubectl_raw(kubeconfig, "get", "pods", "-A", "-o", "json")
    if err:
        return {"error": err, "failed_pods": []}
    try:
        data = orjson.loads(raw)
    except orjson.JSONDecodeError:
        return {"error": "could not parse kubectl output", "failed_pods": []}

    pods: list[dict] = []
    for item in data.get("items", []):
        meta = item.get("metadata", {})
        st = item.get("status", {})
        phase = st.get("phase")
        bad = False
        reason = ""
        restarts = 0
        for cs in (st.get("containerStatuses") or []):
            restarts += int(cs.get("restartCount", 0) or 0)
            state = cs.get("state", {}) or {}
            w, t = state.get("waiting"), state.get("terminated")
            if w and w.get("reason") in BAD_REASONS:
                bad, reason = True, w.get("reason")
            if t and t.get("reason") in BAD_REASONS:
                bad, reason = True, t.get("reason")
            if t and int(t.get("exitCode", 0) or 0) != 0 and t.get("reason") != "Completed":
                bad, reason = True, (t.get("reason") or f"Exit{t.get('exitCode')}")
        for cs in (st.get("initContainerStatuses") or []):
            w = (cs.get("state", {}) or {}).get("waiting")
            if w and w.get("reason") in BAD_REASONS:
                bad, reason = True, "Init:" + w.get("reason")
        if phase in ("Failed", "Unknown"):
            bad = True
            reason = reason or phase
        if bad:
            pods.append({
                "namespace": meta.get("namespace"),
                "pod": meta.get("name"),
                "reason": reason or "NotReady",
                "restarts": restarts,
                "phase": phase,
                "started_at": st.get("startTime"),
            })
    pods.sort(key=lambda x: (x.get("restarts") or 0), reverse=True)
    return {"failed_pods": pods}


# --------------------------------------------------------------------------- #
# Combined scan + cache
# --------------------------------------------------------------------------- #
async def run_scan(app, window_hours: int = DEFAULT_WINDOW_HOURS) -> dict:
    gl_cfg = await _provider_config("gitlab")
    if gl_cfg and gl_cfg.get("report_window_hours"):
        try:
            window_hours = int(gl_cfg["report_window_hours"])
        except (TypeError, ValueError):
            pass
    since = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    kube = await _kube_path()
    group = DEFAULT_GROUP
    gitlab = {"projects_scanned": 0, "failed_pipelines": []}
    kubernetes = {"failed_pods": []}

    if gl_cfg:
        group = str(gl_cfg.get("report_group") or DEFAULT_GROUP)
        try:
            gitlab = await scan_gitlab_failures(gl_cfg, group, since)
        except Exception as exc:  # noqa: BLE001
            logger.error("report_gitlab_scan_failed", extra={"error": str(exc)})
            gitlab = {"projects_scanned": 0, "failed_pipelines": [], "error": str(exc)[:200]}
    if kube:
        try:
            kubernetes = await scan_k8s_failures(kube)
        except Exception as exc:  # noqa: BLE001
            logger.error("report_k8s_scan_failed", extra={"error": str(exc)})
            kubernetes = {"failed_pods": [], "error": str(exc)[:200]}

    result = {
        "generated_at": _now_iso(),
        "window_hours": window_hours,
        "group": group,
        "gitlab": gitlab,
        "kubernetes": kubernetes,
        "summary": {
            "failed_pipelines": len(gitlab.get("failed_pipelines", [])),
            "projects_scanned": gitlab.get("projects_scanned", 0),
            "failed_pods": len(kubernetes.get("failed_pods", [])),
        },
    }

    redis = getattr(app.state, "redis", None) if app else None
    if redis is not None:
        try:
            await redis.set(CACHE_KEY, orjson.dumps(result).decode(), ex=SCAN_INTERVAL_S * 4)
        except Exception:  # noqa: BLE001
            pass
    if app is not None:
        app.state.report_cache = result
    return result


async def get_failures(app) -> dict:
    cached = getattr(app.state, "report_cache", None)
    if cached:
        return cached
    redis = getattr(app.state, "redis", None)
    if redis is not None:
        try:
            blob = await redis.get(CACHE_KEY)
            if blob:
                return orjson.loads(blob)
        except Exception:  # noqa: BLE001
            pass
    return await run_scan(app)


async def background_refresh(app) -> None:
    """Loop forever, refreshing the failures cache. Started in app lifespan."""
    await asyncio.sleep(5)  # let startup settle
    while True:
        try:
            res = await run_scan(app)
            logger.info("report_scanned", extra=res["summary"])
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("report_scan_loop_error")
        await asyncio.sleep(SCAN_INTERVAL_S)


# --------------------------------------------------------------------------- #
# Delivery metrics (deployments per env/day, success rate, bug/feature split)
# --------------------------------------------------------------------------- #
_CLASSIFY_SYS = (
    "You label software-change titles (merge-request titles) for a delivery report. "
    "For each numbered title, output exactly one type:\n"
    "- feature: new functionality, new API/page/screen, add/implement/enhance/support\n"
    "- bugfix: fixing a defect/error/issue/crash; words like fix, bug, issue, hotfix, correct\n"
    "- task: refactor, config, CI/CD, deps, cleanup, docs, db/migration, chore\n"
    "- other: ONLY if you truly cannot tell (avoid this — infer from the verb/noun, "
    "and treat a person's name or ticket id by the action described).\n"
    "Reply with ONLY a JSON array of lowercase strings, same order and length as the "
    "input. No prose, no markdown.\n/no_think"
)
_VALID_TYPES = {"feature", "bugfix", "task", "chore", "other"}


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


async def _llm_classify(app, titles: list[str]) -> list[str]:
    llama = _llama(app)
    if llama is None or not titles:
        return ["other"] * len(titles)
    numbered = "\n".join(f"{i + 1}. {t[:140]}" for i, t in enumerate(titles))
    try:
        msg = await llama.chat(
            messages=[
                {"role": "system", "content": _CLASSIFY_SYS},
                {"role": "user", "content": f"{len(titles)} titles:\n{numbered}"},
            ],
            temperature=0.0,
            top_p=0.9,
            max_tokens=30 + len(titles) * 5,
            model="qwen3-8b",
        )
        content = msg.get("content") or ""
        m = re.search(r"\[.*\]", content, re.S)
        arr = orjson.loads(m.group(0)) if m else []
        types = [str(x).lower().strip() for x in arr]
    except (httpx.HTTPError, orjson.JSONDecodeError, ValueError, KeyError):
        types = []
    types = [t if t in _VALID_TYPES else "other" for t in types]
    if len(types) < len(titles):
        types += ["other"] * (len(titles) - len(types))
    return types[: len(titles)]


async def _classify_breakdown(app, titles: list[str]) -> dict:
    """Classify titles into feature/bugfix/task/chore/other, caching per title."""
    redis = getattr(app.state, "redis", None) if app else None
    recent = [t.strip() for t in titles if t.strip()][:MAX_CLASSIFY]
    uniq = list(dict.fromkeys(recent))
    label: dict[str, str] = {}
    todo: list[str] = []
    for t in uniq:
        key = "clf2:" + hashlib.sha1(t.encode()).hexdigest()
        cached = None
        if redis is not None:
            try:
                cached = await redis.get(key)
            except Exception:  # noqa: BLE001
                cached = None
        if cached:
            label[t] = cached if isinstance(cached, str) else cached.decode()
        else:
            todo.append(t)
    for chunk in _chunks(todo, 30):
        for title, typ in zip(chunk, await _llm_classify(app, chunk)):
            label[title] = typ
            if redis is not None:
                try:
                    await redis.set("clf2:" + hashlib.sha1(title.encode()).hexdigest(), typ, ex=2592000)
                except Exception:  # noqa: BLE001
                    pass
    counts: Counter = Counter()
    for t in recent:
        counts[label.get(t, "other")] += 1
    return dict(counts)


async def scan_delivery(
    app, cfg: dict, group: str, window_days: int = DEFAULT_WINDOW_DAYS,
    do_classify: bool = True, since_iso: str | None = None, until_iso: str | None = None,
) -> dict:
    since = since_iso or (
        datetime.now(timezone.utc) - timedelta(days=window_days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    until = until_iso
    since_date = _local_date(since)
    until_date = _local_date(until) if until else None

    def _in_range(day: str | None) -> bool:
        if not day:
            return True
        if since_date and day < since_date:
            return False
        if until_date and day > until_date:
            return False
        return True

    async with _gl_client(cfg) as client:
        projects = await _group_projects(client, group)
        sem = asyncio.Semaphore(GL_CONCURRENCY)

        async def one(p: dict):
            async with sem:
                deps, jobs, titles = [], [], []
                dep_params = {"updated_after": since, "per_page": 100,
                              "order_by": "updated_at", "sort": "desc"}  # GitLab requires updated_at w/ updated_after
                mr_params = {"state": "merged", "updated_after": since,
                             "per_page": 50, "order_by": "updated_at"}
                if until:
                    dep_params["updated_before"] = until
                    mr_params["updated_before"] = until
                try:
                    r = await client.get(f"/projects/{p['id']}/deployments", params=dep_params)
                    if r.status_code < 400:
                        deps = r.json()
                except httpx.HTTPError:
                    pass
                try:  # deploy-to-X jobs (projects without a GitLab environment)
                    r = await client.get(
                        f"/projects/{p['id']}/jobs",
                        params={"scope[]": "success", "per_page": 100},
                    )
                    if r.status_code < 400:
                        jobs = r.json()
                except httpx.HTTPError:
                    pass
                try:
                    r = await client.get(f"/projects/{p['id']}/merge_requests", params=mr_params)
                    if r.status_code < 400:
                        titles = [m.get("title", "") for m in r.json()]
                except httpx.HTTPError:
                    pass
                return p, deps, jobs, titles

        results = await asyncio.gather(*[one(p) for p in projects])

    by_env: Counter = Counter()
    by_env_day: dict[str, Counter] = defaultdict(Counter)
    person_env: dict = defaultdict(lambda: defaultdict(set))  # key -> env -> {sha}
    person_name: dict[str, str] = {}                          # key -> best display name
    env_commits: dict = defaultdict(set)                      # env -> {sha} (distinct changes)
    person_promo: dict = defaultdict(list)                    # key -> [real-env promotion details]
    promo_seen: set = set()                                   # (key, env, sha)
    lead_times: list = []                                     # commit->real-env deploy seconds (DORA lead time)
    deploy_events: list = []                                  # (project, env, dt, ok) for MTTR
    proj_env_sha: dict = defaultdict(lambda: defaultdict(set))  # project -> env -> {sha} (release readiness)
    proj_ids: dict = {}                                        # project path -> id
    success = failed = 0
    per_project: list[dict] = []
    all_titles: list[str] = []

    for p, deps, jobs, titles in results:
        proj_ids[p.get("path_with_namespace")] = p.get("id")
        proj_env: Counter = Counter()
        proj_success = proj_failed = 0
        last = None
        seen_jobs: set = set()
        # records: (env, day, is_success, status)
        records: list[tuple] = []
        for d in deps:
            job = d.get("deployable") or {}
            jid = job.get("id")
            if jid is not None:
                seen_jobs.add(jid)
            commit = job.get("commit") or {}
            title = commit.get("title") or ""
            records.append((
                _env_bucket((d.get("environment") or {}).get("name")),
                _local_date(d.get("created_at")),
                d.get("status") == "success",
                d.get("status"),
                d.get("created_at"),
                _commit_identity(commit, d.get("user"), title.startswith("Merge ")),
                commit.get("id") or d.get("sha"),
                job.get("ref") or d.get("ref"),
                title,
                commit.get("created_at") or commit.get("authored_date"),
            ))
        for j in jobs:
            m = DEPLOY_JOB_RE.search(j.get("name", "") or "")
            if not m:
                continue
            jid = j.get("id")
            if jid in seen_jobs:  # already counted via the Deployments API
                continue
            seen_jobs.add(jid)
            ts = j.get("finished_at") or j.get("created_at")
            day = _local_date(ts)
            if since_date and day and day < since_date:
                continue
            commit = j.get("commit") or {}
            jtitle = commit.get("title") or ""
            records.append((_env_bucket(m.group(1)), day, True, "success", ts, _commit_identity(commit, j.get("user"), jtitle.startswith("Merge ")), commit.get("id"), j.get("ref"), jtitle, commit.get("created_at") or commit.get("authored_date")))

        for env, day, ok, status, ts, ident, sha, ref, title, ctime in records:
            if not _in_range(day):
                continue
            # MTTR: record every deploy outcome per (project, env)
            edt = _parse_dt(ts)
            if edt and status in ("success", "failed", "canceled"):
                deploy_events.append((p.get("path_with_namespace"), env, edt, ok))
            if ok:
                by_env[env] += 1
                proj_env[env] += 1
                success += 1
                proj_success += 1
                # DORA lead time: commit authored -> reached a real environment
                if env in REAL_ENVS and ctime and ts:
                    cdt, ddt = _parse_dt(ctime), _parse_dt(ts)
                    if cdt and ddt and ddt > cdt:
                        lead_times.append((ddt - cdt).total_seconds())
                display, key = ident
                if sha:
                    env_commits[env].add(sha)          # distinct changes reaching this env (incl. merges)
                    proj_env_sha[p.get("path_with_namespace")][env].add(sha)
                # GitLab UI merge commits ("Merge branch 'X' into 'Y'") are integration
                # actions performed via a shared seat — don't credit them to a person.
                ui_merge = (title or "").startswith("Merge branch '") and "' into '" in (title or "")
                if key and sha and not ui_merge:
                    person_env[key][env].add(sha)      # distinct commit per person per env
                    if key not in person_name or (display and not person_name[key]):
                        person_name[key] = display
                    if env in REAL_ENVS:
                        sig = (key, env, sha)
                        if sig not in promo_seen:
                            promo_seen.add(sig)
                            person_promo[key].append({
                                "project": p.get("path_with_namespace"),
                                "env": env, "ref": ref, "sha": (sha or "")[:10],
                                "date": day, "title": (title or "")[:120],
                            })
                if day:
                    by_env_day[day][env] += 1
                if not last or (ts or "") > last:
                    last = ts
            elif status in ("failed", "canceled"):
                failed += 1
                proj_failed += 1

        all_titles.extend(titles)
        if proj_success or proj_failed or titles:
            per_project.append({
                "project": p.get("path_with_namespace"),
                "deploys": dict(proj_env),
                "success": proj_success,
                "failed": proj_failed,
                "last_deploy": last,
                "merged_mrs": len(titles),
            })

    breakdown = await _classify_breakdown(app, all_titles) if do_classify else {}
    per_day = [
        {"date": day, "by_env": dict(by_env_day[day]), "total": sum(by_env_day[day].values())}
        for day in sorted(by_env_day)
    ]
    per_project.sort(key=lambda x: x["success"], reverse=True)

    # per-customer rollup (account-level view for leadership)
    cust_map: dict = defaultdict(lambda: {"deploys": Counter(), "failed": 0, "mrs": 0, "projects": 0})
    for pp in per_project:
        cust = _customer_of(pp["project"])
        for e, n in pp["deploys"].items():
            cust_map[cust]["deploys"][e] += n
        cust_map[cust]["failed"] += pp.get("failed", 0)
        cust_map[cust]["mrs"] += pp.get("merged_mrs", 0)
        cust_map[cust]["projects"] += 1
    per_customer = []
    for cust, v in cust_map.items():
        dep = dict(v["deploys"])
        per_customer.append({
            "customer": cust,
            "deploys": sum(dep.values()),
            "real": sum(n for e, n in dep.items() if e in REAL_ENVS),
            "dev": dep.get("DEV", 0),
            "by_env": dep,
            "failed": v["failed"],
            "mrs": v["mrs"],
            "projects": v["projects"],
        })
    per_customer.sort(key=lambda x: -x["deploys"])

    # DORA: lead time (median commit->real-env) + MTTR (median failure->recovery)
    lead_hours = round(statistics.median(lead_times) / 3600.0, 1) if lead_times else None
    by_pe: dict = defaultdict(list)
    for proj, env, edt, ok in deploy_events:
        by_pe[(proj, env)].append((edt, ok))
    recoveries: list = []
    for evs in by_pe.values():
        evs.sort(key=lambda x: x[0])
        fail_at = None
        for edt, ok in evs:
            if not ok and fail_at is None:
                fail_at = edt
            elif ok and fail_at is not None:
                recoveries.append((edt - fail_at).total_seconds())
                fail_at = None
    mttr_hours = round(statistics.median(recoveries) / 3600.0, 1) if recoveries else None

    # Release readiness: distinct changes that reached pre-prod (SIT/DEMO/UAT/PREPROD)
    # but NOT PROD yet — the production release backlog.
    pre_prod = {"SIT", "DEMO", "UAT", "PREPROD"}
    release_backlog = []
    for proj, envs in proj_env_sha.items():
        pre: set = set().union(*[envs[e] for e in pre_prod if e in envs]) if any(e in envs for e in pre_prod) else set()
        pending = pre - envs.get("PROD", set())
        if pending:
            release_backlog.append({
                "project": proj,
                "project_id": proj_ids.get(proj),
                "customer": _customer_of(proj),
                "pending": len(pending),
                "reached": [e for e in ENV_ORDER if e in envs and e in REAL_ENVS],
            })
    release_backlog.sort(key=lambda x: -x["pending"])

    total = success + failed
    today = (datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)).strftime("%Y-%m-%d")

    return {
        "generated_at": _now_iso(),
        "window_days": window_days,
        "group": group,
        "totals": {
            "deployments": success,
            "failed_deployments": failed,
            "success_rate": round(100 * success / total, 1) if total else 100.0,
            "change_failure_rate": round(100 * failed / total, 1) if total else 0.0,
            "by_env": {e: by_env.get(e, 0) for e in ENV_ORDER if by_env.get(e)},
            "today": sum(by_env_day.get(today, {}).values()),
            "real_changes": len(set().union(*[env_commits[e] for e in env_commits if e in REAL_ENVS]) if any(e in REAL_ENVS for e in env_commits) else set()),
            "prod_changes": len(env_commits.get("PROD", set())),
            "lead_time_hours": lead_hours,
            "mttr_hours": mttr_hours,
        },
        "funnel": {e: len(env_commits[e]) for e in ENV_ORDER if env_commits.get(e)},
        "work_breakdown": breakdown,
        "merged_mrs": len(all_titles),
        "per_day": per_day,
        "per_project": per_project[:60],
        "per_customer": per_customer,
        "release_backlog": release_backlog[:40],
        "top_deployers": _person_rows(person_env, person_name, person_promo),
    }


async def run_delivery(app, window_days: int = DEFAULT_WINDOW_DAYS) -> dict:
    cfg = await _provider_config("gitlab")
    if not cfg:
        return {"generated_at": _now_iso(), "group": DEFAULT_GROUP, "totals": {},
                "per_day": [], "per_project": [], "work_breakdown": {}, "error": "GitLab not configured"}
    group = str(cfg.get("report_group") or DEFAULT_GROUP)
    if cfg.get("report_window_days"):
        try:
            window_days = int(cfg["report_window_days"])
        except (TypeError, ValueError):
            pass
    try:
        result = await scan_delivery(app, cfg, group, window_days)
    except Exception as exc:  # noqa: BLE001
        logger.exception("delivery_scan_failed")
        return {"generated_at": _now_iso(), "group": group, "totals": {},
                "per_day": [], "per_project": [], "work_breakdown": {}, "error": str(exc)[:200]}
    redis = getattr(app.state, "redis", None) if app else None
    if redis is not None:
        try:
            await redis.set(DELIVERY_CACHE_KEY, orjson.dumps(result).decode(), ex=DELIVERY_INTERVAL_S * 3)
        except Exception:  # noqa: BLE001
            pass
    if app is not None:
        app.state.delivery_cache = result
    return result


async def get_delivery(app) -> dict:
    cached = getattr(app.state, "delivery_cache", None)
    if cached:
        return cached
    redis = getattr(app.state, "redis", None)
    if redis is not None:
        try:
            blob = await redis.get(DELIVERY_CACHE_KEY)
            if blob:
                return orjson.loads(blob)
        except Exception:  # noqa: BLE001
            pass
    return await run_delivery(app)


def _customer_of(path: str) -> str:
    """Customer/account from a project path: the product family's leading token
    (e.g. g360_greenfield->g360, celcomdigi_exorabe->celcomdigi, regopshub->regopshub)."""
    parts = [
        p for p in (path or "").split("/")
        if p.lower() not in ("dol", "code8-backend", "code8-frontend", "others", "coe")
    ]
    if not parts:
        return "other"
    seg = re.split(r"[_-]", parts[0])[0]
    return seg or parts[0]


def _product_of(path: str) -> str:
    """Best-effort product/customer line from a GitLab project path."""
    parts = [
        p for p in (path or "").split("/")
        if p.lower() not in ("dol", "code8-backend", "code8-frontend", "others")
    ]
    if not parts:
        return "other"
    seg = re.sub(r"[_-](fe|be|backend|frontend|service|connector|api)$", "", parts[0], flags=re.I)
    return seg or parts[0] or "other"


async def get_overview(app) -> dict:
    """CEO/CTO one-glance summary, synthesised from the failures + delivery caches."""
    failures = await get_failures(app)
    delivery = await get_delivery(app)
    fk = failures.get("kubernetes", {}) or {}
    fg = failures.get("gitlab", {}) or {}
    dt = delivery.get("totals", {}) or {}
    wb = delivery.get("work_breakdown", {}) or {}

    prod: dict[str, dict] = defaultdict(lambda: {"deploys": 0, "mrs": 0, "by_env": Counter()})
    for p in delivery.get("per_project", []):
        key = _product_of(p.get("project", ""))
        prod[key]["deploys"] += sum(p.get("deploys", {}).values())
        prod[key]["mrs"] += p.get("merged_mrs", 0)
        for e, n in p.get("deploys", {}).items():
            prod[key]["by_env"][e] += n
    products = sorted(
        ({"product": k, "deploys": v["deploys"], "mrs": v["mrs"], "by_env": dict(v["by_env"])}
         for k, v in prod.items()),
        key=lambda x: x["deploys"], reverse=True,
    )[:15]

    worst_pods = sorted(fk.get("failed_pods", []), key=lambda x: x.get("restarts", 0), reverse=True)[:6]
    pipe_proj = Counter(pl.get("project") for pl in fg.get("failed_pipelines", []))
    pipe_by_cust = Counter(_customer_of(pl.get("project", "")) for pl in fg.get("failed_pipelines", []))
    per_customer = [
        {**c, "failed_pipelines": pipe_by_cust.get(c["customer"], 0)}
        for c in (delivery.get("per_customer") or [])
    ]

    return {
        "generated_at": _now_iso(),
        "group": delivery.get("group", DEFAULT_GROUP),
        "window_days": delivery.get("window_days", DEFAULT_WINDOW_DAYS),
        "headline": {
            "deploys_window": dt.get("deployments", 0),
            "deploys_today": dt.get("today", 0),
            "success_rate": dt.get("success_rate", 0),
            "change_failure_rate": dt.get("change_failure_rate", 0),
            "real_changes": dt.get("real_changes", 0),
            "prod_changes": dt.get("prod_changes", 0),
            "lead_time_hours": dt.get("lead_time_hours"),
            "mttr_hours": dt.get("mttr_hours"),
            "features": wb.get("feature", 0),
            "bugfixes": wb.get("bugfix", 0),
            "failing_pods": len(fk.get("failed_pods", [])),
            "failed_pipelines": len(fg.get("failed_pipelines", [])),
            "projects_scanned": fg.get("projects_scanned", 0),
        },
        "by_env": dt.get("by_env", {}),
        "funnel": delivery.get("funnel", {}),
        "work_breakdown": wb,
        "per_day": delivery.get("per_day", []),
        "products": products,
        "per_customer": per_customer,
        "top_deployers": delivery.get("top_deployers", []),
        "attention": {
            "pods": [
                {"namespace": p["namespace"], "pod": p["pod"], "reason": p["reason"], "restarts": p["restarts"]}
                for p in worst_pods
            ],
            "pipelines": [{"project": proj, "count": cnt} for proj, cnt in pipe_proj.most_common(6)],
        },
    }


def _local_date_to_utc_iso(date_str: str, end: bool = False) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    if end:
        d = d + timedelta(days=1)
    return (d - timedelta(hours=TZ_OFFSET_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")


async def build_export(app, from_date: str, to_date: str) -> dict:
    """On-demand report for an explicit local date range (for download/PDF)."""
    cfg = await _provider_config("gitlab")
    if not cfg:
        return {"error": "GitLab is not configured", "from": from_date, "to": to_date}
    group = str(cfg.get("report_group") or DEFAULT_GROUP)
    since = _local_date_to_utc_iso(from_date)
    until = _local_date_to_utc_iso(to_date, end=True)

    delivery = await scan_delivery(app, cfg, group, since_iso=since, until_iso=until, do_classify=True)

    failed_pipelines: list[dict] = []
    try:
        gl = await scan_gitlab_failures(cfg, group, since)
        failed_pipelines = [
            p for p in gl.get("failed_pipelines", [])
            if from_date <= (_local_date(p.get("created_at")) or "9999") <= to_date
        ]
    except Exception:  # noqa: BLE001
        logger.exception("export_pipeline_scan_failed")

    pods: list[dict] = []
    kube = await _kube_path()
    if kube:
        try:
            pods = (await scan_k8s_failures(kube)).get("failed_pods", [])
        except Exception:  # noqa: BLE001
            logger.exception("export_k8s_scan_failed")

    return {
        "generated_at": _now_iso(),
        "group": group,
        "from": from_date,
        "to": to_date,
        "delivery": delivery,
        "failed_pipelines": failed_pipelines,
        "failing_pods": pods,
    }


async def background_delivery_refresh(app) -> None:
    await asyncio.sleep(20)
    while True:
        try:
            res = await run_delivery(app)
            logger.info("delivery_scanned", extra={"deployments": res.get("totals", {}).get("deployments")})
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("delivery_loop_error")
        await asyncio.sleep(DELIVERY_INTERVAL_S)


# --------------------------------------------------------------------------- #
# LLM root-cause analysis
# --------------------------------------------------------------------------- #
_ANALYST_SYS = (
    "You are a senior DevOps/SRE engineer. You are given diagnostics from a FAILED "
    "CI pipeline or a failing Kubernetes pod. Respond in short markdown with exactly "
    "these sections:\n"
    "**What failed** — one line.\n"
    "**Root cause** — the specific error and why it happened; quote the key log line(s).\n"
    "**Fix** — the most likely remediation steps.\n"
    "Base everything on the evidence; do not invent. If the logs are inconclusive, say "
    "so and name what to check next.\n/no_think"
)


def _llama(app):
    if app is None:
        return None
    clients = getattr(app.state, "llama_clients", {})
    return clients.get("qwen3-8b") or getattr(app.state, "llama", None)


async def _stream_analysis(app, content: str) -> AsyncIterator[str]:
    llama = _llama(app)
    if llama is None:
        yield "Inference is not available."
        return
    async for kind, delta in llama.stream_chat(
        messages=[
            {"role": "system", "content": _ANALYST_SYS},
            {"role": "user", "content": content[:12000]},
        ],
        temperature=0.2,
        top_p=0.9,
        max_tokens=700,
        model="qwen3-8b",
    ):
        if kind == "content":
            yield delta


async def analyze_pipeline(app, project_id: int, pipeline_id: int) -> AsyncIterator[str]:
    cfg = await _provider_config("gitlab")
    if not cfg:
        yield "GitLab is not configured."
        return
    blocks: list[str] = []
    async with _gl_client(cfg) as c:
        r = await c.get(
            f"/projects/{project_id}/pipelines/{pipeline_id}/jobs",
            params={"per_page": 50},
        )
        jobs = [j for j in (r.json() if r.status_code < 400 else []) if j.get("status") == "failed"]
        for j in jobs[:3]:
            tr = await c.get(f"/projects/{project_id}/jobs/{j['id']}/trace")
            trace = tr.text if tr.status_code < 400 else ""
            if trace.strip():
                blocks.append(f"### Failed job: {j.get('name')} (stage: {j.get('stage')})\n{trace[-2600:]}")
    if not blocks:
        yield "No failed-job logs were available for this pipeline (it may have failed before any job ran, or logs expired)."
        return
    content = (
        f"A GitLab CI pipeline (#{pipeline_id}) failed. Below are the tail logs of its "
        f"failed job(s):\n\n" + "\n\n".join(blocks)
    )
    async for delta in _stream_analysis(app, content):
        yield delta
    yield "\n\n---\n\n**Evidence — actual GitLab job log (tail):**\n\n```\n"
    yield ("\n\n".join(blocks))[-1600:]
    yield "\n```\n"


async def analyze_pod(app, namespace: str, pod: str) -> AsyncIterator[str]:
    kube = await _kube_path()
    if not kube:
        yield "Kubernetes is not configured."
        return
    describe = await k8s_provider._run_kubectl(kube, "describe", "pod", "-n", namespace, pod, timeout=20.0)
    cur, _ = await _kubectl_raw(kube, "logs", "-n", namespace, pod, "--tail=120", "--all-containers=true", timeout=20.0)
    prev, _ = await _kubectl_raw(kube, "logs", "-n", namespace, pod, "--previous", "--tail=120", "--all-containers=true", timeout=20.0)
    events = await k8s_provider._run_kubectl(
        kube, "get", "events", "-n", namespace,
        "--field-selector", f"involvedObject.name={pod}", "--sort-by=.lastTimestamp", timeout=20.0,
    )
    blocks: list[str] = []
    if prev and prev.strip():
        blocks.append("### Previous (crashed) container logs:\n" + prev[-2600:])
    if cur and cur.strip():
        blocks.append("### Current logs:\n" + cur[-1500:])
    if events and "no resources" not in events.lower():
        blocks.append("### Events:\n" + events[-1500:])
    if describe:
        blocks.append("### Describe (tail):\n" + describe[-2000:])
    content = f"Kubernetes pod {namespace}/{pod} is failing. Diagnostics:\n\n" + "\n\n".join(blocks)
    async for delta in _stream_analysis(app, content):
        yield delta
    yield "\n\n---\n\n**Evidence — actual pod logs / events (tail):**\n\n```\n"
    yield ("\n\n".join(blocks))[-1600:]
    yield "\n```\n"


async def release_notes(app, project_id: int, days: int = 14) -> AsyncIterator[str]:
    """Stream AI-written release notes for a project, from its merged MRs."""
    cfg = await _provider_config("gitlab")
    if not cfg:
        yield "GitLab is not configured."
        return
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    async with _gl_client(cfg) as c:
        r = await c.get(
            f"/projects/{project_id}/merge_requests",
            params={"state": "merged", "updated_after": since, "per_page": 60, "order_by": "updated_at"},
        )
        mrs = r.json() if r.status_code < 400 else []
    if not mrs:
        yield f"No merged merge-requests in the last {days} days to summarise."
        return
    items = "\n".join(
        f"- {m.get('title', '')} (by {_user_name(m.get('author'))})" for m in mrs[:60]
    )
    sys = (
        "You are a release manager. From the merged merge-request titles below, write clean "
        "release notes for stakeholders. Group into **Features**, **Fixes**, **Improvements**, "
        "**Other** (omit empty groups); one concise human-readable bullet each; merge duplicates; "
        "drop noise (chore/lint/merge). Markdown only, no preamble.\n/no_think"
    )
    llama = _llama(app)
    if llama is None:
        yield "Inference is not available."
        return
    async for kind, delta in llama.stream_chat(
        messages=[{"role": "system", "content": sys}, {"role": "user", "content": f"Merged changes:\n{items[:10000]}"}],
        temperature=0.3, top_p=0.9, max_tokens=750, model="qwen3-8b",
    ):
        if kind == "content":
            yield delta


# --------------------------------------------------------------------------- #
# Weekly AI digest (narrative summary for leadership; optional Slack delivery)
# --------------------------------------------------------------------------- #
_DIGEST_SYS = (
    "You are an engineering chief of staff. Write a crisp WEEKLY Delivery & Reliability "
    "digest for the CEO/CTO from the metrics below. Use these markdown sections: "
    "**Headline** (1-2 sentences), **Delivery** (what shipped & where), **Reliability** "
    "(what's broken / risk), **Customers** (notable per-account movement), **Action items** "
    "(2-4 bullets). Be specific with the numbers, concise, plain business language. No preamble.\n/no_think"
)


async def _digest_content(app) -> str:
    o = await get_overview(app)
    h = o.get("headline", {})
    parts = [
        f"Window: {o.get('window_days')} days · group {o.get('group')} · {h.get('projects_scanned')} projects.",
        f"Deployments: {h.get('deploys_window')} ({h.get('real_changes')} reached real envs, "
        f"{h.get('prod_changes')} to PROD). Success {h.get('success_rate')}%, change-failure {h.get('change_failure_rate')}%. "
        f"Lead time {h.get('lead_time_hours')}h, MTTR {h.get('mttr_hours')}h.",
        f"Velocity: {h.get('features')} features, {h.get('bugfixes')} fixes shipped.",
        f"Reliability: {h.get('failing_pods')} failing pods, {h.get('failed_pipelines')} failed pipelines.",
        "By customer: " + "; ".join(
            f"{c['customer']} {c['deploys']} deploys/{c.get('failed_pipelines', c.get('failed', 0))} fail"
            for c in o.get("per_customer", [])[:8]),
        "Promotion funnel: " + ", ".join(f"{e}:{n}" for e, n in o.get("funnel", {}).items()),
        "Top contributors (real-env): " + ", ".join(
            f"{p['user']}({p['real']})" for p in o.get("top_deployers", [])[:6] if p.get("real")),
        "Worst pods: " + "; ".join(
            f"{p['pod']} {p['restarts']}x" for p in o.get("attention", {}).get("pods", [])[:4]),
    ]
    return "\n".join(parts)


async def stream_digest(app) -> AsyncIterator[str]:
    content = await _digest_content(app)
    llama = _llama(app)
    if llama is None:
        yield "Inference is not available."
        return
    async for kind, delta in llama.stream_chat(
        messages=[{"role": "system", "content": _DIGEST_SYS}, {"role": "user", "content": content}],
        temperature=0.3, top_p=0.9, max_tokens=850, model="qwen3-8b",
    ):
        if kind == "content":
            yield delta


async def generate_digest_text(app) -> str:
    content = await _digest_content(app)
    llama = _llama(app)
    if llama is None:
        return "Inference is not available."
    msg = await llama.chat(
        messages=[{"role": "system", "content": _DIGEST_SYS}, {"role": "user", "content": content}],
        temperature=0.3, top_p=0.9, max_tokens=850, model="qwen3-8b",
    )
    return msg.get("content") or ""


def _digest_html(md: str) -> str:
    """Render the digest markdown (headings as **bold** lines, '- ' bullets,
    inline **bold**) into a simple, email-client-safe HTML body."""
    def inline(s: str) -> str:
        s = _html.escape(s)
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)

    out: list[str] = []
    in_list = False
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        stripped = line.strip()
        bullet = stripped.startswith(("- ", "* ")) or re.match(r"^\d+\.\s", stripped)
        if bullet:
            if not in_list:
                out.append('<ul style="margin:4px 0 10px 0;padding-left:20px">')
                in_list = True
            item = re.sub(r"^([-*]\s|\d+\.\s)", "", stripped)
            out.append(f'<li style="margin:2px 0">{inline(item)}</li>')
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        # a line that is only **Heading** -> section header
        m = re.fullmatch(r"\*\*(.+?)\*\*", stripped)
        if m:
            out.append(f'<h3 style="margin:14px 0 4px 0;font-size:15px;color:#111827">{_html.escape(m.group(1))}</h3>')
        else:
            out.append(f'<p style="margin:4px 0;line-height:1.5">{inline(stripped)}</p>')
    if in_list:
        out.append("</ul>")
    body = "\n".join(out)
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'font-size:14px;color:#1f2937;max-width:680px;margin:0 auto">'
        '<div style="border-bottom:2px solid #2563eb;padding-bottom:8px;margin-bottom:12px">'
        '<span style="font-size:18px;font-weight:700;color:#111827">OpsGPT</span>'
        '<span style="color:#6b7280;font-size:13px"> · Weekly Delivery &amp; Reliability digest</span></div>'
        f"{body}"
        '<p style="margin-top:18px;color:#9ca3af;font-size:11px">'
        'Auto-generated by OpsGPT from live GitLab &amp; Kubernetes data.</p></div>'
    )


def _smtp_send_sync(recipients: list[str], subject: str, text: str, html_body: str) -> None:
    msg = EmailMessage()
    sender = settings.smtp_from or settings.smtp_user
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=25) as s:
        s.ehlo()
        if settings.smtp_starttls:
            s.starttls()
            s.ehlo()
        if settings.smtp_user and settings.smtp_password:
            s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)


async def send_email(recipients: list[str], subject: str, text: str) -> tuple[bool, str]:
    """Send a markdown body as a styled HTML email (plain-text fallback)."""
    recipients = [r.strip() for r in recipients if r and r.strip()]
    if not recipients:
        return False, "No recipients configured."
    if not settings.smtp_user:
        return False, "No sending mailbox configured (set OPSGPT_SMTP_USER)."
    try:
        await asyncio.to_thread(_smtp_send_sync, recipients, subject, text, _digest_html(text))
        return True, f"Emailed {len(recipients)} recipient(s)."
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {str(exc)[:200]}"


async def send_digest_email(text: str, subject: str = "OpsGPT — Weekly Delivery & Reliability digest") -> tuple[bool, str]:
    recipients = [r.strip() for r in settings.digest_to.split(",") if r.strip()]
    if not recipients:
        return False, "No recipients configured (set OPSGPT_DIGEST_TO)."
    return await send_email(recipients, subject, text)


async def background_digest(app) -> None:
    """Once-a-day check: if it's the configured digest day/hour and not already
    sent today, generate the digest and email it to the recipients."""
    if not settings.digest_enabled or not settings.digest_to or not settings.smtp_user:
        return
    last_sent = None
    while True:
        try:
            now_local = datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)
            today = now_local.date()
            if (now_local.weekday() == settings.digest_day
                    and now_local.hour >= settings.digest_hour
                    and last_sent != today):
                text = await generate_digest_text(app)
                ok, msg = await send_digest_email(text)
                last_sent = today
                logger.info("digest_sent", extra={"ok": ok, "msg": msg})
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("digest_loop_error")
        await asyncio.sleep(1800)  # check every 30 min


# --------------------------------------------------------------------------- #
# Self-test (run inside the backend container)
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    async def _main():
        await _selftest()
        await _delivery_test()

    async def _selftest():
        res = await run_scan(None, window_hours=72)
        print("group:", res["group"], "| summary:", res["summary"])
        print("\nfailed pipelines (top 8):")
        for p in res["gitlab"]["failed_pipelines"][:8]:
            print("  ", p["project"], "#", p["pipeline_id"], p["ref"], "by", p.get("user", "?"))
        if res["gitlab"].get("error"):
            print("  gitlab error:", res["gitlab"]["error"])
        print("\nfailed pods (top 12):")
        for p in res["kubernetes"]["failed_pods"][:12]:
            print("  ", p["namespace"], "/", p["pod"], "->", p["reason"], "restarts", p["restarts"])
        if res["kubernetes"].get("error"):
            print("  k8s error:", res["kubernetes"]["error"])

    async def _delivery_test():
        cfg = await _provider_config("gitlab")
        print("\n===== DELIVERY (7d, no classify) =====")
        d = await scan_delivery(None, cfg, DEFAULT_GROUP, 7, do_classify=False)
        print("totals:", d["totals"])
        print("per_day:")
        for row in d["per_day"]:
            print("  ", row["date"], row["by_env"], "total", row["total"])
        print("top projects by deploys:")
        for p in d["per_project"][:8]:
            print("  ", p["project"], p["deploys"], "mrs", p["merged_mrs"])
        print("merged MRs in window:", d["merged_mrs"], "(classification runs in-app with the LLM)")
        print("change failure rate:", d["totals"].get("change_failure_rate"), "| real_changes:", d["totals"].get("real_changes"), "| prod:", d["totals"].get("prod_changes"))
        print("funnel:", d.get("funnel"))
        print("top deployers (real | dev):", [(x["user"], x["real"], x["dev"]) for x in d.get("top_deployers", [])[:8]])

    asyncio.run(_main())
