"""Client for the nomic-embed llama.cpp server (OpenAI /v1/embeddings).

nomic-embed-text-v1.5 expects task prefixes: 'search_document:' for indexed
chunks and 'search_query:' for queries. We apply them here.
"""

from __future__ import annotations

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbedError(RuntimeError):
    pass


class EmbedClient:
    def __init__(
        self,
        base_url: str,
        *,
        batch_size: int = 16,
        doc_prefix: str = "search_document: ",
        query_prefix: str = "search_query: ",
    ) -> None:
        # Task prefixes differ per model: nomic uses 'search_document:'/'search_query:';
        # BGE uses no doc prefix and a retrieval instruction on the query.
        self._client = httpx.AsyncClient(base_url=base_url, timeout=120.0)
        self._batch = batch_size
        self._doc_prefix = doc_prefix
        self._query_prefix = query_prefix

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> bool:
        try:
            r = await self._client.get("/health")
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def _embed_raw(self, inputs: list[str]) -> list[list[float]]:
        try:
            resp = await self._client.post(
                "/v1/embeddings", json={"input": inputs, "model": "nomic"}
            )
            if resp.status_code != 200:
                raise EmbedError(f"embed server {resp.status_code}: {resp.text[:300]}")
            data = resp.json()["data"]
            data.sort(key=lambda d: d.get("index", 0))
            return [d["embedding"] for d in data]
        except httpx.HTTPError as exc:
            raise EmbedError(f"failed to reach embed server: {exc}") from exc

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self._batch):
            batch = [f"{self._doc_prefix}{t}" for t in texts[i : i + self._batch]]
            out.extend(await self._embed_raw(batch))
        return out

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed_raw([f"{self._query_prefix}{text}"]))[0]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts verbatim (no task prefix) — for the public /v1/embeddings API."""
        out: list[list[float]] = []
        for i in range(0, len(texts), self._batch):
            out.extend(await self._embed_raw(texts[i : i + self._batch]))
        return out
