"""Liveness and readiness probes (used by Docker/K8s and the admin dashboard)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    """Process is up. Cheap, no dependencies."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request, response: Response) -> dict[str, object]:
    """Ready to serve traffic — verifies the inference upstream is reachable."""
    client = request.app.state.llama
    upstream_ok = await client.health()

    redis = getattr(request.app.state, "redis", None)
    redis_ok = False
    if redis is not None:
        try:
            redis_ok = bool(await redis.ping())
        except Exception:  # noqa: BLE001
            redis_ok = False

    if not upstream_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if upstream_ok else "degraded",
        "inference": upstream_ok,
        "redis": redis_ok,
    }
