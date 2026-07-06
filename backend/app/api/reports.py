"""Delivery & Reliability reports: failures overview + LLM root-cause analysis."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Literal

import orjson
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import get_current_user, require_role
from app.db.models import Role, User
from app.services import alert_service, grc_report, report_service

router = APIRouter(prefix="/reports", tags=["reports"])
admin_only = require_role(Role.admin.value)

_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9.\-]{0,251}[a-z0-9])?$", re.IGNORECASE)


@router.get("/failures", summary="Cached failures overview (GitLab pipelines + K8s pods)")
async def failures(request: Request, _: User = Depends(get_current_user)) -> dict:
    return await report_service.get_failures(request.app)


@router.get("/overview", summary="CEO/CTO one-glance summary (delivery + reliability)")
async def overview(request: Request, _: User = Depends(get_current_user)) -> dict:
    return await report_service.get_overview(request.app)


@router.post("/digest", summary="Stream an AI weekly delivery & reliability digest")
async def digest(request: Request, _: User = Depends(get_current_user)) -> StreamingResponse:
    gen = report_service.stream_digest(request.app)

    async def sse() -> AsyncIterator[str]:
        try:
            async for delta in gen:
                yield f"data: {orjson.dumps({'type': 'token', 'content': delta}).decode()}\n\n"
        except Exception:  # noqa: BLE001
            yield f"data: {orjson.dumps({'type': 'error', 'message': 'Digest generation failed.'}).decode()}\n\n"
        yield f"data: {orjson.dumps({'type': 'done'}).decode()}\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/digest/send", summary="Generate the digest and email it to the team (admin)")
async def digest_send(request: Request, _: User = Depends(admin_only)) -> dict:
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.digest_to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No recipients configured (set OPSGPT_DIGEST_TO).")
    if not settings.smtp_user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No sending mailbox configured (set OPSGPT_SMTP_USER).")
    text = await report_service.generate_digest_text(request.app)
    ok, msg = await report_service.send_digest_email(text)
    return {"ok": ok, "message": msg}


@router.get("/alerts", summary="Live failure alerts (newly failed pipelines/pods + AI fix)")
async def alerts(request: Request, _: User = Depends(get_current_user)) -> dict:
    return await alert_service.get_alerts(request.app)


class AckRequest(BaseModel):
    id: str | None = None  # None = acknowledge all


@router.post("/alerts/ack", summary="Acknowledge one alert (or all when id omitted)")
async def alerts_ack(body: AckRequest, request: Request, _: User = Depends(get_current_user)) -> dict:
    return await alert_service.ack_alert(request.app, body.id)


@router.post("/alerts/clear", summary="Clear the alert feed (admin)")
async def alerts_clear(request: Request, _: User = Depends(admin_only)) -> dict:
    return await alert_service.clear_alerts(request.app)


@router.post("/alerts/scan", summary="Force one alert-detection cycle now (admin)")
async def alerts_scan(request: Request, _: User = Depends(admin_only)) -> dict:
    new = await alert_service.scan_and_alert(request.app)
    return {"new": len(new), "alerts": new}


_ENV_RE = re.compile(r"^[a-z0-9]{1,20}$", re.IGNORECASE)


@router.get("/compliance", summary="GRC compliance posture for an environment (fleet + per-platform + assets)")
async def compliance(request: Request, env: str = Query("dev"), _: User = Depends(get_current_user)) -> dict:
    if not _ENV_RE.match(env):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid env")
    return await grc_report.compliance_overview(request.app, env)


@router.get("/compliance/asset", summary="Controls for one asset's latest scan (drill-down)")
async def compliance_asset(
    request: Request,
    asset: str = Query(..., min_length=1, max_length=200),
    env: str = Query("dev"),
    status_: str = Query("failed", alias="status"),
    _: User = Depends(get_current_user),
) -> dict:
    if not _ENV_RE.match(env):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid env")
    return await grc_report.asset_controls(request.app, asset, env, status_)


@router.get("/compliance/control", summary="One control's status + command + evidence (pass or fail)")
async def compliance_control(
    request: Request,
    asset: str = Query(..., min_length=1, max_length=200),
    control_id: str = Query(..., min_length=1, max_length=120),
    env: str = Query("dev"),
    _: User = Depends(get_current_user),
) -> dict:
    if not _ENV_RE.match(env):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid env")
    return await grc_report.control_detail(request.app, asset, control_id, env)


@router.post("/compliance/summary", summary="Stream an AI compliance-officer brief for an environment")
async def compliance_summary(request: Request, env: str = Query("dev"), _: User = Depends(get_current_user)) -> StreamingResponse:
    if not _ENV_RE.match(env):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid env")
    gen = grc_report.stream_compliance_summary(request.app, env)

    async def sse() -> AsyncIterator[str]:
        try:
            async for delta in gen:
                yield f"data: {orjson.dumps({'type': 'token', 'content': delta}).decode()}\n\n"
        except Exception:  # noqa: BLE001
            yield f"data: {orjson.dumps({'type': 'error', 'message': 'Summary failed.'}).decode()}\n\n"
        yield f"data: {orjson.dumps({'type': 'done'}).decode()}\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/delivery", summary="Delivery metrics: deployments per env/day, success rate, bug/feature split")
async def delivery(request: Request, _: User = Depends(get_current_user)) -> dict:
    return await report_service.get_delivery(request.app)


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@router.get("/export", summary="Generate a report for an explicit date range (for download/PDF)")
async def export_report(
    request: Request,
    from_: str = Query(alias="from"),
    to: str = Query(...),
    _: User = Depends(get_current_user),
) -> dict:
    if not (_DATE_RE.match(from_) and _DATE_RE.match(to)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "from/to must be YYYY-MM-DD")
    if from_ > to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "'from' must be on or before 'to'")
    return await report_service.build_export(request.app, from_, to)


@router.post("/refresh", summary="Force a fresh failures scan (admin)")
async def refresh(request: Request, _: User = Depends(admin_only)) -> dict:
    return await report_service.run_scan(request.app)


class AnalyzeRequest(BaseModel):
    type: Literal["pipeline", "pod"]
    project_id: int | None = None
    pipeline_id: int | None = None
    namespace: str | None = None
    pod: str | None = None


class ReleaseNotesRequest(BaseModel):
    project_id: int
    days: int = 14


@router.post("/release-notes", summary="Stream AI-written release notes for a project")
async def release_notes(
    body: ReleaseNotesRequest, request: Request, _: User = Depends(get_current_user)
) -> StreamingResponse:
    gen = report_service.release_notes(request.app, body.project_id, body.days)

    async def sse() -> AsyncIterator[str]:
        try:
            async for delta in gen:
                yield f"data: {orjson.dumps({'type': 'token', 'content': delta}).decode()}\n\n"
        except Exception:  # noqa: BLE001
            yield f"data: {orjson.dumps({'type': 'error', 'message': 'Release-notes generation failed.'}).decode()}\n\n"
        yield f"data: {orjson.dumps({'type': 'done'}).decode()}\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/analyze", summary="Stream an AI root-cause analysis for one failure")
async def analyze(
    body: AnalyzeRequest, request: Request, _: User = Depends(get_current_user)
) -> StreamingResponse:
    app = request.app
    if body.type == "pipeline":
        if not body.project_id or not body.pipeline_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "project_id and pipeline_id are required")
        gen = report_service.analyze_pipeline(app, body.project_id, body.pipeline_id)
    else:
        ns, pod = body.namespace or "", body.pod or ""
        if not (_NAME_RE.match(ns) and _NAME_RE.match(pod)):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "valid namespace and pod are required")
        gen = report_service.analyze_pod(app, ns, pod)

    async def sse() -> AsyncIterator[str]:
        try:
            async for delta in gen:
                yield f"data: {orjson.dumps({'type': 'token', 'content': delta}).decode()}\n\n"
        except Exception:  # noqa: BLE001
            yield f"data: {orjson.dumps({'type': 'error', 'message': 'Analysis failed.'}).decode()}\n\n"
        yield f"data: {orjson.dumps({'type': 'done'}).decode()}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
