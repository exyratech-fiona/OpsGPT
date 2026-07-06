"""Live failure alerting.

A background monitor reads the failures cache (GitLab failed pipelines + K8s
failing pods), detects ones it has not alerted on yet (deduped in Redis), asks
the LLM *what went wrong and how to fix it*, and pushes each new alert onto an
in-app feed (and, when SMTP is configured, emails it).

The heavy scanning is reused from ``report_service`` so there is a single source
of truth; this module only adds the "new vs. already-seen" + delivery layer.
"""

from __future__ import annotations

import asyncio

import orjson

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services import report_service

logger = get_logger(__name__)
settings = get_settings()

FEED_KEY = "alerts:feed"          # JSON list of recent alert objects (newest first)
SEEN_PREFIX = "alerts:seen:"      # per-failure dedup marker
SEEN_TTL_S = 7 * 24 * 3600        # re-alert the same failure at most once a week
FEED_MAX = 100                    # cap the in-app feed length
ANALYSIS_MAX_CHARS = 6000         # trim very long AI analyses before storing


# --------------------------------------------------------------------------- #
# Dedup + feed storage (Redis with in-process fallback)
# --------------------------------------------------------------------------- #
async def _claim(app, key: str) -> bool:
    """Return True the first time we see ``key`` (atomically), else False."""
    redis = getattr(app.state, "redis", None)
    if redis is not None:
        try:
            ok = await redis.set(SEEN_PREFIX + key, "1", ex=SEEN_TTL_S, nx=True)
            return bool(ok)
        except Exception:  # noqa: BLE001
            pass
    seen = getattr(app.state, "alert_seen", None)
    if seen is None:
        seen = app.state.alert_seen = set()
    if key in seen:
        return False
    seen.add(key)
    return True


async def _load_feed(app) -> list[dict]:
    redis = getattr(app.state, "redis", None)
    if redis is not None:
        try:
            blob = await redis.get(FEED_KEY)
            if blob:
                return orjson.loads(blob)
        except Exception:  # noqa: BLE001
            pass
    return list(getattr(app.state, "alert_feed", []) or [])


async def _save_feed(app, feed: list[dict]) -> None:
    feed = feed[:FEED_MAX]
    app.state.alert_feed = feed
    redis = getattr(app.state, "redis", None)
    if redis is not None:
        try:
            await redis.set(FEED_KEY, orjson.dumps(feed).decode())
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
# Public API used by the routes
# --------------------------------------------------------------------------- #
async def get_alerts(app) -> dict:
    feed = await _load_feed(app)
    unread = sum(1 for a in feed if not a.get("acked"))
    return {"alerts": feed, "unread": unread, "count": len(feed)}


async def ack_alert(app, alert_id: str | None) -> dict:
    """Acknowledge one alert by id, or all when ``alert_id`` is None."""
    feed = await _load_feed(app)
    for a in feed:
        if alert_id is None or a.get("id") == alert_id:
            a["acked"] = True
    await _save_feed(app, feed)
    return await get_alerts(app)


async def clear_alerts(app) -> dict:
    await _save_feed(app, [])
    return {"alerts": [], "unread": 0, "count": 0}


# --------------------------------------------------------------------------- #
# Detection + analysis
# --------------------------------------------------------------------------- #
async def _collect(agen) -> str:
    parts: list[str] = []
    async for delta in agen:
        parts.append(delta)
        if sum(len(p) for p in parts) > ANALYSIS_MAX_CHARS:
            break
    return "".join(parts).strip()[:ANALYSIS_MAX_CHARS]


async def _email_alert(alert: dict) -> None:
    if not settings.alerts_email:
        return
    recipients = settings.alerts_to or settings.digest_to
    rcpts = [r.strip() for r in recipients.split(",") if r.strip()]
    if not rcpts:
        return
    icon = "🔴" if alert["kind"] == "pod" else "🟠"
    subject = f"{icon} OpsGPT alert — {alert['kind']}: {alert['title']}"
    body = (
        f"**{alert['title']}**\n\n"
        f"- Type: {alert['kind']}\n"
        f"- When: {alert['detected_at']}\n"
        + (f"- Link: {alert['web_url']}\n" if alert.get("web_url") else "")
        + f"\n{alert['analysis']}"
    )
    ok, msg = await report_service.send_email(rcpts, subject, body)
    logger.info("alert_emailed", extra={"ok": ok, "msg": msg, "id": alert["id"]})


async def scan_and_alert(app) -> list[dict]:
    """One detection cycle. Returns the newly-created alerts."""
    data = await report_service.get_failures(app)
    gl = (data.get("gitlab") or {}).get("failed_pipelines") or []
    pods = (data.get("kubernetes") or {}).get("failed_pods") or []

    new: list[dict] = []
    budget = settings.alerts_max_per_cycle

    for pl in gl:
        if budget <= 0:
            break
        key = f"pipe:{pl.get('project_id')}:{pl.get('pipeline_id')}"
        if not await _claim(app, key):
            continue
        budget -= 1
        project = (pl.get("project") or "").split("/")[-1] or pl.get("project") or "?"
        try:
            analysis = await _collect(
                report_service.analyze_pipeline(app, pl["project_id"], pl["pipeline_id"])
            )
        except Exception:  # noqa: BLE001 — never lose the alert over an analysis error
            logger.exception("alert_pipeline_analysis_failed", extra={"id": key})
            analysis = "_AI analysis unavailable right now — open in GitLab for the job logs._"
        new.append({
            "id": key,
            "kind": "pipeline",
            "title": f"{project} · {pl.get('ref') or '?'}",
            "project": pl.get("project"),
            "project_id": pl.get("project_id"),
            "pipeline_id": pl.get("pipeline_id"),
            "ref": pl.get("ref"),
            "web_url": pl.get("web_url"),
            "created_at": pl.get("created_at"),
            "detected_at": report_service._now_iso(),
            "analysis": analysis,
            "acked": False,
        })

    for pod in pods:
        if budget <= 0:
            break
        key = f"pod:{pod.get('namespace')}:{pod.get('pod')}"
        if not await _claim(app, key):
            continue
        budget -= 1
        try:
            analysis = await _collect(
                report_service.analyze_pod(app, pod["namespace"], pod["pod"])
            )
        except Exception:  # noqa: BLE001 — never lose the alert over an analysis error
            logger.exception("alert_pod_analysis_failed", extra={"id": key})
            analysis = "_AI analysis unavailable right now — check the pod logs/events directly._"
        new.append({
            "id": key,
            "kind": "pod",
            "title": f"{pod.get('namespace')} · {pod.get('pod')}",
            "namespace": pod.get("namespace"),
            "pod": pod.get("pod"),
            "reason": pod.get("reason"),
            "restarts": pod.get("restarts"),
            "web_url": None,
            "created_at": pod.get("started_at"),
            "detected_at": report_service._now_iso(),
            "analysis": analysis,
            "acked": False,
        })

    if new:
        feed = await _load_feed(app)
        await _save_feed(app, new + feed)
        for a in new:
            try:
                await _email_alert(a)
            except Exception:  # noqa: BLE001
                logger.exception("alert_email_failed")
        logger.info("alerts_raised", extra={"count": len(new)})
    return new


async def background_monitor(app) -> None:
    """Periodically detect newly-failed pipelines/pods and raise alerts."""
    if not settings.alerts_enabled:
        return
    app.state.alert_feed = []
    await asyncio.sleep(20)  # let the first failures scan populate the cache
    while True:
        try:
            await scan_and_alert(app)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("alert_monitor_error")
        await asyncio.sleep(settings.alerts_interval_s)
