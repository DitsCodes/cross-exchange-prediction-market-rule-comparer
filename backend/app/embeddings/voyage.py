"""Voyage AI embedding client (Anthropic's recommended embedding pairing)."""

from __future__ import annotations

import asyncio
import logging
from typing import Iterable

from app.config import get_settings

logger = logging.getLogger(__name__)


class VoyageEmbedder:
    """Thin wrapper around the voyageai SDK.

    The SDK is sync, so we run calls in a thread to keep the event loop free.
    """

    BATCH_SIZE = 128

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.voyage_api_key
        self._model = model or settings.voyage_model
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import voyageai  # type: ignore
            except ImportError as e:
                raise RuntimeError(
                    "voyageai package not installed; add it to dependencies."
                ) from e
            if not self._api_key:
                raise RuntimeError("VOYAGE_API_KEY is not configured.")
            self._client = voyageai.Client(api_key=self._api_key)
        return self._client

    async def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        items = list(texts)
        if not items:
            return []
        out: list[list[float]] = []
        for i in range(0, len(items), self.BATCH_SIZE):
            batch = items[i : i + self.BATCH_SIZE]
            embeddings = await asyncio.to_thread(self._embed_sync, batch, "document")
            out.extend(embeddings)
        return out

    async def embed_query(self, text: str) -> list[float]:
        result = await asyncio.to_thread(self._embed_sync, [text], "query")
        return result[0]

    def _embed_sync(self, batch: list[str], input_type: str) -> list[list[float]]:
        client = self._get_client()
        result = client.embed(batch, model=self._model, input_type=input_type)
        return list(result.embeddings)


_embedder: VoyageEmbedder | None = None


def get_embedder() -> VoyageEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = VoyageEmbedder()
    return _embedder
