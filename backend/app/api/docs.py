"""Document management endpoints for RAG (upload / list / delete)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import get_db
from app.db.models import Document, User
from app.schemas.docs import DocumentOut
from app.services import rag

logger = get_logger(__name__)
# NOTE: prefix is /documents (NOT /docs) to avoid colliding with FastAPI's
# Swagger UI mounted at /api/docs.
router = APIRouter(prefix="/documents", tags=["documents"])
settings = get_settings()

_ALLOWED_EXT = (".pdf", ".txt", ".md", ".markdown", ".log", ".yaml", ".yml", ".json", ".csv")


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list:
    res = await db.execute(
        select(Document)
        .where(Document.user_id == user.id)
        .order_by(Document.created_at.desc())
    )
    return list(res.scalars().all())


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Document:
    filename = file.filename or "upload"
    if not filename.lower().endswith(_ALLOWED_EXT):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed: {', '.join(_ALLOWED_EXT)}",
        )

    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_mb} MB limit.",
        )
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")

    doc = Document(
        user_id=user.id,
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        status="pending",
    )
    db.add(doc)
    await db.flush()  # assign doc.id for chunk FKs

    embed = request.app.state.rag_embed
    try:
        count = await rag.ingest(db, embed, doc, data)
    except Exception as exc:
        logger.error("ingest_failed", extra={"error": str(exc), "file": filename})
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not process document: {exc}",
        )

    doc.chunk_count = count
    doc.status = "ready"
    await db.flush()
    await db.refresh(doc)
    logger.info("document_ingested", extra={"file": filename, "chunks": count})
    return doc


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    res = await db.execute(
        select(Document).where(Document.id == doc_id, Document.user_id == user.id)
    )
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.delete(doc)  # cascades to chunks
    return {"status": "deleted"}
