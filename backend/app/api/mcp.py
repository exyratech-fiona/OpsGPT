"""Configurable MCP servers — discovery (all users) + management (admin)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.db.base import get_db
from app.db.models import McpServer, Role, User
from app.schemas.mcp import (
    McpServerCreate,
    McpServerOut,
    McpServerUpdate,
    McpTestRequest,
    McpTestResult,
)
from app.core.netguard import UnsafeUrlError
from app.services import mcp_service

router = APIRouter(prefix="/mcp", tags=["mcp"])
admin_only = require_role(Role.admin.value)


def _guard_url(provider_type: str, config: dict) -> None:
    try:
        mcp_service.assert_config_url_safe(provider_type, config)
    except UnsafeUrlError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsafe URL: {exc}")


def _to_out(s: McpServer) -> McpServerOut:
    return McpServerOut(
        id=s.id,
        name=s.name,
        provider_type=s.provider_type,
        display_name=mcp_service.DISPLAY.get(s.provider_type, s.provider_type),
        enabled=s.enabled,
        status=s.status,
        status_message=s.status_message,
        config=mcp_service.public_config(s.config or {}),
        tools=mcp_service.tools_of(s),
        created_at=s.created_at,
    )


@router.get("/providers", response_model=list[McpServerOut])
async def list_providers(
    _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list:
    res = await db.execute(select(McpServer).order_by(McpServer.name))
    return [_to_out(s) for s in res.scalars().all()]


@router.post("/servers", response_model=McpServerOut, status_code=status.HTTP_201_CREATED)
async def create_server(
    body: McpServerCreate,
    request: Request,
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
) -> McpServerOut:
    if (await db.execute(select(McpServer).where(McpServer.name == body.name))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A server with that name already exists")
    _guard_url(body.provider_type, body.config)
    ok, msg = await mcp_service.test_connection(body.provider_type, body.config)
    server = McpServer(
        name=body.name,
        provider_type=body.provider_type,
        config=body.config,
        enabled=body.enabled,
        status="ok" if ok else "error",
        status_message=msg,
    )
    db.add(server)
    await db.flush()
    await db.refresh(server)
    await db.commit()
    await mcp_service.load_registries(request.app)
    return _to_out(server)


@router.patch("/servers/{server_id}", response_model=McpServerOut)
async def update_server(
    server_id: uuid.UUID,
    body: McpServerUpdate,
    request: Request,
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
) -> McpServerOut:
    server = await db.get(McpServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    if body.name is not None:
        server.name = body.name
    if body.enabled is not None:
        server.enabled = body.enabled
    if body.config is not None:
        server.config = mcp_service.merge_config(server.config or {}, body.config)
        _guard_url(server.provider_type, server.config)
        ok, msg = await mcp_service.test_connection(server.provider_type, server.config)
        server.status = "ok" if ok else "error"
        server.status_message = msg
    await db.flush()
    await db.commit()
    await mcp_service.load_registries(request.app)
    return _to_out(server)


@router.delete("/servers/{server_id}")
async def delete_server(
    server_id: uuid.UUID,
    request: Request,
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    server = await db.get(McpServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    await db.delete(server)
    await db.commit()
    await mcp_service.load_registries(request.app)
    return {"status": "deleted"}


@router.post("/servers/{server_id}/test", response_model=McpTestResult)
async def test_saved(
    server_id: uuid.UUID,
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
) -> McpTestResult:
    server = await db.get(McpServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    ok, msg = await mcp_service.test_connection(server.provider_type, server.config or {})
    server.status = "ok" if ok else "error"
    server.status_message = msg
    await db.flush()
    await db.commit()
    return McpTestResult(ok=ok, message=msg)


@router.post("/test", response_model=McpTestResult)
async def test_config(
    body: McpTestRequest,
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
) -> McpTestResult:
    """Test a (possibly unsaved) config. If server_id is given, secrets left blank
    are taken from the saved server so they needn't be re-entered."""
    config = body.config
    if body.server_id:
        existing = await db.get(McpServer, body.server_id)
        if existing:
            config = mcp_service.merge_config(existing.config or {}, body.config)
    ok, msg = await mcp_service.test_connection(body.provider_type, config)
    return McpTestResult(ok=ok, message=msg)
