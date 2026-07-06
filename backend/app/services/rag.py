"""RAG pipeline: extract -> chunk -> embed -> store, and similarity retrieval."""

from __future__ import annotations

import hashlib
import io
import re
import uuid

import orjson
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import DocChunk, Document
from app.services.embed_client import EmbedClient

logger = get_logger(__name__)
settings = get_settings()

_WS = re.compile(r"[ \t]+")


def _normalize(text: str) -> str:
    text = text.replace("\x00", " ")
    text = _WS.sub(" ", text)
    return text.strip()


def extract_pages(filename: str, content_type: str, data: bytes) -> list[tuple[int | None, str]]:
    """Return [(page_number_or_None, text), ...]."""
    is_pdf = filename.lower().endswith(".pdf") or "pdf" in content_type
    if is_pdf:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
    # text-like (txt, md, log, yaml, json, ...)
    return [(None, data.decode("utf-8", "replace"))]


def chunk_pages(
    pages: list[tuple[int | None, str]], size: int, overlap: int
) -> list[tuple[int | None, str]]:
    chunks: list[tuple[int | None, str]] = []
    for page, raw in pages:
        text = _normalize(raw)
        if not text:
            continue
        start = 0
        n = len(text)
        while start < n:
            end = min(start + size, n)
            chunks.append((page, text[start:end]))
            if end >= n:
                break
            start = max(end - overlap, start + 1)
    return chunks


async def ingest(
    db: AsyncSession, embed: EmbedClient, document: Document, data: bytes
) -> int:
    """Extract, chunk, embed and persist a document's chunks. Returns chunk count."""
    pages = extract_pages(document.filename, document.content_type, data)
    chunks = chunk_pages(pages, settings.chunk_chars, settings.chunk_overlap)
    if not chunks:
        raise ValueError("No extractable text found in the document.")

    vectors = await embed.embed_documents([c for _, c in chunks])
    for idx, ((page, content), vector) in enumerate(zip(chunks, vectors)):
        db.add(
            DocChunk(
                document_id=document.id,
                user_id=document.user_id,
                chunk_index=idx,
                page=page,
                content=content,
                embedding=vector,
            )
        )
    return len(chunks)


async def _query_embedding(embed: EmbedClient, redis, query: str) -> list[float]:
    """Embed the query, using a Redis cache keyed by the query text if available."""
    key = "emb:" + hashlib.sha256(query.encode("utf-8")).hexdigest()
    if redis is not None:
        try:
            cached = await redis.get(key)
            if cached:
                return orjson.loads(cached)
        except Exception:  # noqa: BLE001
            pass
    vec = await embed.embed_query(query)
    if redis is not None:
        try:
            await redis.set(key, orjson.dumps(vec), ex=settings.embed_cache_ttl_s)
        except Exception:  # noqa: BLE001
            pass
    return vec


async def retrieve(
    db: AsyncSession,
    embed: EmbedClient,
    *,
    user_id: uuid.UUID,
    query: str,
    top_k: int,
    document_ids: list[uuid.UUID] | None = None,
    redis=None,
    reranker=None,
    candidates: int = 20,
) -> list[tuple[DocChunk, str, float]]:
    """Return [(chunk, filename, distance), ...] most relevant to the query.

    Two-stage when a reranker is provided: fetch `candidates` nearest by embedding
    (good recall), then a cross-encoder rescores them and we keep `top_k` (good
    precision). Without a reranker it's plain top_k embedding search.
    """
    qvec = await _query_embedding(embed, redis, query)
    fetch_n = max(top_k, candidates) if reranker is not None else top_k
    distance = DocChunk.embedding.cosine_distance(qvec).label("distance")
    stmt = (
        select(DocChunk, Document.filename, distance)
        .join(Document, Document.id == DocChunk.document_id)
        .where(DocChunk.user_id == user_id)
        .where(DocChunk.embedding.isnot(None))
    )
    if document_ids:
        stmt = stmt.where(DocChunk.document_id.in_(document_ids))
    stmt = stmt.order_by(distance).limit(fetch_n)
    rows = [(row[0], row[1], float(row[2])) for row in (await db.execute(stmt)).all()]

    # Second stage: rerank the candidates and keep the best top_k. Falls back to
    # the embedding order if the reranker is unavailable.
    if reranker is not None and len(rows) > top_k:
        try:
            ranked = await reranker.rerank(query, [c.content for c, _, _ in rows], top_n=top_k)
            if ranked:
                out: list[tuple[DocChunk, str, float]] = []
                for idx, score in ranked[:top_k]:
                    if 0 <= idx < len(rows):
                        chunk, filename, _ = rows[idx]
                        out.append((chunk, filename, 1.0 - score))  # pseudo-distance
                if out:
                    return out
        except Exception as exc:  # noqa: BLE001 — never let rerank break retrieval
            logger.warning("rerank_failed", extra={"error": str(exc)})
    return rows[:top_k]


def build_context(results: list[tuple[DocChunk, str, float]]) -> tuple[str, list[dict]]:
    """Build the context block injected into the prompt + a citations list."""
    blocks: list[str] = []
    citations: list[dict] = []
    for i, (chunk, filename, dist) in enumerate(results, start=1):
        loc = f"{filename}" + (f" p.{chunk.page}" if chunk.page else "")
        blocks.append(f"[{i}] (source: {loc})\n{chunk.content}")
        citations.append(
            {
                "index": i,
                "filename": filename,
                "page": chunk.page,
                "score": round(1.0 - dist, 3),
            }
        )
    return "\n\n".join(blocks), citations
