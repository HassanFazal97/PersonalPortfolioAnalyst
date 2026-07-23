"""Voyage AI embedding client — plain httpx against the REST endpoint, no SDK.

Anthropic has no embeddings API and recommends Voyage. ``input_type`` matters:
documents are embedded as "document", recall queries as "query" (asymmetric
encoding is a free retrieval-quality win). Costs are tracked in USD like
MODEL_PRICES; the recall tool charges them to the run's Budget via
``record_flat_cost``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

import httpx

from app.config import embedding_price_for, get_settings

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.voyageai.com/v1/embeddings"
_BATCH_SIZE = 128  # Voyage recommends <=128 texts per request
_TIMEOUT_SECONDS = 10.0
_RETRIES = 2

InputType = Literal["document", "query"]


class EmbeddingClient:
    """Batching, retrying Voyage client. ``enabled`` is the feature switch —
    all callers must check it (or use module helpers that do)."""

    def __init__(
        self, *, api_key: str | None = None, model: str | None = None
    ) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.voyage_api_key
        self.model = model or settings.embedding_model
        self.cost_usd = 0.0  # cumulative, across calls on this instance

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def embed(
        self, texts: list[str], *, input_type: InputType
    ) -> list[list[float]]:
        """Embed texts (order-preserving). Raises on failure after retries —
        callers decide whether that's fatal (recall tool) or ignorable
        (fire-and-forget ingestion)."""
        if not self.enabled:
            raise RuntimeError("embeddings disabled: VOYAGE_API_KEY is not set")
        out: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            out.extend(await self._embed_batch(texts[start : start + _BATCH_SIZE], input_type))
        return out

    async def _embed_batch(
        self, batch: list[str], input_type: InputType
    ) -> list[list[float]]:
        payload = {"model": self.model, "input": batch, "input_type": input_type}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        attempt = 0
        while True:
            attempt += 1
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                    resp = await client.post(_ENDPOINT, json=payload, headers=headers)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(
                        f"retryable status {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                data = resp.json()
                tokens = int((data.get("usage") or {}).get("total_tokens", 0) or 0)
                self.cost_usd += tokens * embedding_price_for(self.model) / 1_000_000
                by_index = sorted(data["data"], key=lambda d: d["index"])
                return [d["embedding"] for d in by_index]
            except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.TransportError):
                if attempt > _RETRIES:
                    raise
                await asyncio.sleep(0.5 * attempt)


def get_embedding_client() -> EmbeddingClient:
    return EmbeddingClient()


def memory_enabled(settings: Any | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.voyage_api_key)
