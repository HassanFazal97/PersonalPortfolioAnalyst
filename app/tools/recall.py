"""recall_memory tool: semantic search over this user's own history
(digests, stored news, prior chat answers) in the pgvector memory store.

Offered to chats only when VOYAGE_API_KEY is set (see app/main.py::
_prepare_chat, same gating pattern as WEB_SEARCH_TOOL). Failures raise —
the loop's safe_dispatch converts them into is_error tool_results."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from app.config import DEFAULT_USER_ID
from app.memory.embeddings import EmbeddingClient

_OWNER_USER_ID = uuid.UUID(DEFAULT_USER_ID)

_SOURCE_TYPES = {"digest", "news", "chat", "alert"}


def _parse_date(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD)") from exc


async def recall_memory(payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
    query = str(payload["query"]).strip()
    if not query:
        raise ValueError("query must be a non-empty string")
    date_from = _parse_date(payload.get("date_from"), "date_from")
    date_to = _parse_date(payload.get("date_to"), "date_to")

    if ctx.repo is None:
        raise RuntimeError("recall_memory requires database access")
    client = EmbeddingClient()
    if not client.enabled:
        raise RuntimeError("semantic memory is not configured on this deployment")
    tickers = [str(t).upper() for t in payload.get("tickers") or []]
    source_types = [
        s for s in (payload.get("source_types") or []) if s in _SOURCE_TYPES
    ]
    k = min(
        int(payload.get("max_results") or ctx.settings.memory_recall_max_results), 12
    )

    [vector] = await client.embed([query], input_type="query")
    # The embed call is real spend; attribute it to this run's budget.
    if getattr(ctx, "budget", None) is not None:
        ctx.budget.record_flat_cost(client.cost_usd)

    rows = await ctx.repo.search_memory(
        user_id=ctx.user_id or _OWNER_USER_ID,
        embedding=vector,
        k=k,
        tickers=tickers or None,
        date_from=date_from,
        date_to=date_to,
        source_types=source_types or None,
    )
    return {
        "count": len(rows),
        "items": [
            {
                "content": chunk.content,
                "source_type": chunk.source_type,
                "date": chunk.content_date.isoformat(),
                "tickers": chunk.tickers or [],
                # Cosine distance -> similarity, for the model's ranking sense.
                "score": round(1.0 - distance, 2),
            }
            for chunk, distance in rows
        ],
    }
