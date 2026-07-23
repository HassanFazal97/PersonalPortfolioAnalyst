"""Memory ingestion: chunk freshly-persisted content and embed it, fire-and-
forget. Every entrypoint is fail-open — an embedding outage must never break
a digest, news refresh, or chat response. Missed rows are healed by re-running
``scripts/backfill_memory.py`` (idempotent via the chunks' unique key)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime
from typing import Any

from app.db.repo import digest_mentions_ticker
from app.memory.embeddings import EmbeddingClient, get_embedding_client

logger = logging.getLogger(__name__)

# Q&A chunks split at paragraph boundaries around this size; digests and news
# items are short enough to embed whole.
_CHAT_CHUNK_CHARS = 1600

# Strong refs so fire-and-forget tasks aren't garbage-collected mid-flight.
_tasks: set[asyncio.Task] = set()


def schedule(coro) -> None:
    """Run ``coro`` in the background, swallowing (but logging) any failure."""

    async def guarded():
        try:
            await coro
        except Exception:  # noqa: BLE001 - ingestion is strictly best-effort
            logger.warning("memory ingestion failed", exc_info=True)

    try:
        task = asyncio.get_running_loop().create_task(guarded())
    except RuntimeError:  # no running loop (sync tests) — skip silently
        coro.close()
        return
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


# ---- chunkers (pure, unit-testable) ----------------------------------------


def chunk_chat(question: str, answer: str, *, max_chars: int = _CHAT_CHUNK_CHARS) -> list[str]:
    """One "Q: …\\nA: …" text, split at paragraph boundaries when long."""
    text = f"Q: {question.strip()}\nA: {answer.strip()}"
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = para
        else:
            current = candidate
    if current:
        chunks.append(current)
    # A single paragraph longer than max_chars still gets hard-split.
    out: list[str] = []
    for c in chunks:
        while len(c) > max_chars:
            out.append(c[:max_chars])
            c = c[max_chars:]
        out.append(c)
    return out


def news_content(ticker: str, headline: str, summary: str | None) -> str:
    body = f"{ticker}: {headline}"
    if summary:
        body += f" — {summary}"
    return body


def mentioned_tickers(text: str, holdings: list[str]) -> list[str]:
    return [t for t in holdings if digest_mentions_ticker(text, t)]


# ---- ingestion entrypoints (call via schedule()) ----------------------------


async def embed_digest(
    repo: Any,
    *,
    user_id: uuid.UUID,
    digest_id: uuid.UUID,
    body: str,
    digest_date: date,
    holdings_tickers: list[str],
    client: EmbeddingClient | None = None,
) -> int:
    client = client or get_embedding_client()
    if not client.enabled or not body:
        return 0
    [vector] = await client.embed([body], input_type="document")
    return await repo.upsert_memory_chunks(
        [
            {
                "user_id": user_id,
                "source_type": "digest",
                "source_id": digest_id,
                "chunk_index": 0,
                "content": body,
                "tickers": mentioned_tickers(body, holdings_tickers),
                "content_date": digest_date,
                "embedding": vector,
                "embedding_model": client.model,
            }
        ]
    )


async def embed_news_items(
    repo: Any,
    *,
    user_id: uuid.UUID,
    rows: list[Any],
    client: EmbeddingClient | None = None,
) -> int:
    """Rows are persisted NewsItem records (id, ticker, headline, summary,
    published_at/created_at)."""
    client = client or get_embedding_client()
    if not client.enabled or not rows:
        return 0
    texts = [
        news_content(r.ticker, r.headline, getattr(r, "summary", None)) for r in rows
    ]
    vectors = await client.embed(texts, input_type="document")
    chunks = []
    for r, text, vector in zip(rows, texts, vectors):
        when = getattr(r, "published_at", None) or getattr(r, "created_at", None)
        content_date = when.date() if isinstance(when, datetime) else date.today()
        chunks.append(
            {
                "user_id": user_id,
                "source_type": "news",
                "source_id": r.id,
                "chunk_index": 0,
                "content": text,
                "tickers": [r.ticker],
                "content_date": content_date,
                "embedding": vector,
                "embedding_model": client.model,
            }
        )
    return await repo.upsert_memory_chunks(chunks)


async def embed_chat_run(
    repo: Any,
    *,
    user_id: uuid.UUID,
    run_id: uuid.UUID,
    question: str,
    answer: str,
    created_at: datetime | None,
    holdings_tickers: list[str],
    client: EmbeddingClient | None = None,
) -> int:
    client = client or get_embedding_client()
    if not client.enabled or not question or not answer:
        return 0
    texts = chunk_chat(question, answer)
    vectors = await client.embed(texts, input_type="document")
    when = created_at.date() if created_at else date.today()
    tickers = mentioned_tickers(f"{question}\n{answer}", holdings_tickers)
    return await repo.upsert_memory_chunks(
        [
            {
                "user_id": user_id,
                "source_type": "chat",
                "source_id": run_id,
                "chunk_index": i,
                "content": text,
                "tickers": tickers,
                "content_date": when,
                "embedding": vector,
                "embedding_model": client.model,
            }
            for i, (text, vector) in enumerate(zip(texts, vectors))
        ]
    )
