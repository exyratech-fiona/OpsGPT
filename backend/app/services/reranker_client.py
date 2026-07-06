"""Client for the bge-reranker-v2-m3 llama.cpp server (reranking endpoint).

A cross-encoder: given a query and candidate documents, it returns a relevance
score per document so RAG can reorder the embedding results and keep the best few.
"""

from __future__ import annotations

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


class RerankerError(RuntimeError):
    pass


class RerankerClient:
    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=60.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def rerank(
        self, query: str, documents: list[str], top_n: int | None = None
    ) -> list[tuple[int, float]]:
        """Return [(original_index, relevance_score), ...] sorted best-first."""
        if not documents:
            return []
        payload: dict = {"query": query, "documents": documents}
        if top_n is not None:
            payload["top_n"] = top_n
        try:
            resp = await self._client.post("/v1/rerank", json=payload)
            if resp.status_code != 200:
                raise RerankerError(f"reranker {resp.status_code}: {resp.text[:200]}")
            results = resp.json().get("results", [])
        except httpx.HTTPError as exc:
            raise RerankerError(f"failed to reach reranker: {exc}") from exc
        pairs = [
            (int(r["index"]), float(r.get("relevance_score", r.get("score", 0.0))))
            for r in results
            if "index" in r
        ]
        pairs.sort(key=lambda x: x[1], reverse=True)
        return pairs
