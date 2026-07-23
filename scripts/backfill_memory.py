"""Backfill semantic memory from existing digests, news items, and chat runs.

Idempotent: memory_chunks' (user_id, source_type, source_id, chunk_index)
unique key makes re-runs insert only what's missing — this is also the healing
mechanism after a Voyage outage window, since live ingestion is fire-and-forget.

Usage:
  python scripts/backfill_memory.py --dry-run          # count + estimate cost
  python scripts/backfill_memory.py                    # all users
  python scripts/backfill_memory.py --user <uuid> --limit 500
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.models import AgentRun, Digest, MemoryChunk, NewsItem  # noqa: E402
from app.db.repo import Repo  # noqa: E402
from app.memory import ingest  # noqa: E402
from app.memory.embeddings import EmbeddingClient  # noqa: E402

# ~4 chars/token; used only for the --dry-run cost estimate.
_CHARS_PER_TOKEN = 4

# Free-tier Voyage keys allow ~3 requests/min; the runtime client fails fast
# (chat can't wait), but a one-off backfill can afford to sit out 429 windows.
_RATE_LIMIT_WAIT_SECONDS = 25.0
_RATE_LIMIT_MAX_WAITS = 60


async def _patient(coro_factory):
    """Run an ingest step, waiting out Voyage 429s instead of crashing."""
    for _ in range(_RATE_LIMIT_MAX_WAITS):
        try:
            return await coro_factory()
        except httpx.HTTPStatusError as e:
            if e.response is None or e.response.status_code != 429:
                raise
            print(f"  rate limited — waiting {_RATE_LIMIT_WAIT_SECONDS:.0f}s", flush=True)
            await asyncio.sleep(_RATE_LIMIT_WAIT_SECONDS)
    raise SystemExit("still rate limited after repeated waits; re-run to continue")


async def _existing_source_ids(repo: Repo, user_id, source_type) -> set:
    async with repo._session() as s:  # noqa: SLF001 - script-local convenience
        rows = await s.execute(
            select(MemoryChunk.source_id).where(
                MemoryChunk.user_id == user_id,
                MemoryChunk.source_type == source_type,
            )
        )
        return {r[0] for r in rows.all()}


async def _user_rows(repo: Repo, model, *filters, limit: int | None):
    async with repo._session() as s:  # noqa: SLF001
        stmt = select(model).where(*filters)
        if limit:
            stmt = stmt.limit(limit)
        return list((await s.execute(stmt)).scalars().all())


async def backfill_user(
    repo: Repo,
    client: EmbeddingClient,
    user_id: uuid.UUID,
    *,
    holdings: list[str],
    limit: int | None,
    dry_run: bool,
    max_cost: float,
) -> dict:
    counts = {"digest": 0, "news": 0, "chat": 0, "est_tokens": 0}

    digests = await _user_rows(repo, Digest, Digest.user_id == user_id, limit=limit)
    have = await _existing_source_ids(repo, user_id, "digest")
    digests = [d for d in digests if d.id not in have]

    news_rows = await _user_rows(repo, NewsItem, NewsItem.user_id == user_id, limit=limit)
    have = await _existing_source_ids(repo, user_id, "news")
    news_rows = [n for n in news_rows if n.id not in have]

    chats = await _user_rows(
        repo,
        AgentRun,
        AgentRun.user_id == user_id,
        AgentRun.trigger == "chat",
        AgentRun.status.in_(("completed", "budget_exceeded", "max_iterations")),
        AgentRun.final_answer.is_not(None),
        limit=limit,
    )
    have = await _existing_source_ids(repo, user_id, "chat")
    chats = [c for c in chats if c.id not in have]

    if dry_run:
        chars = (
            sum(len(d.body or "") for d in digests)
            + sum(len(n.headline or "") + len(n.summary or "") for n in news_rows)
            + sum(len(c.user_message or "") + len(c.final_answer or "") for c in chats)
        )
        counts.update(
            digest=len(digests), news=len(news_rows), chat=len(chats),
            est_tokens=chars // _CHARS_PER_TOKEN,
        )
        return counts

    for d in digests:
        if client.cost_usd >= max_cost:
            print(f"  cost cap ${max_cost} reached — aborting; re-run to continue")
            break
        counts["digest"] += await _patient(lambda d=d: ingest.embed_digest(
            repo, user_id=user_id, digest_id=d.id, body=d.body,
            digest_date=d.digest_date, holdings_tickers=holdings, client=client,
        ))
    if news_rows and client.cost_usd < max_cost:
        counts["news"] += await _patient(lambda: ingest.embed_news_items(
            repo, user_id=user_id, rows=news_rows, client=client
        ))
    for c in chats:
        if client.cost_usd >= max_cost:
            print(f"  cost cap ${max_cost} reached — aborting; re-run to continue")
            break
        counts["chat"] += await _patient(lambda c=c: ingest.embed_chat_run(
            repo, user_id=user_id, run_id=c.id, question=c.user_message,
            answer=c.final_answer, created_at=c.created_at,
            holdings_tickers=holdings, client=client,
        ))
    return counts


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--user", type=uuid.UUID, default=None)
    parser.add_argument("--limit", type=int, default=None, help="max rows per source per user")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set")
    client = EmbeddingClient()
    if not client.enabled and not args.dry_run:
        raise SystemExit("VOYAGE_API_KEY is not set (use --dry-run to just count)")

    repo = Repo(settings.database_url, ssl=settings.db_ssl)
    try:
        if args.user:
            user_ids = [args.user]
        else:
            async with repo._session() as s:  # noqa: SLF001
                from app.db.models import User

                user_ids = [
                    r[0] for r in (await s.execute(select(User.id))).all()
                ]
        total_cost_cap = settings.memory_backfill_max_cost_usd
        est_tokens = 0
        for uid in user_ids:
            positions = await repo.list_positions(user_id=uid)
            holdings = sorted({p.ticker for p in positions})
            counts = await backfill_user(
                repo, client, uid,
                holdings=holdings, limit=args.limit,
                dry_run=args.dry_run, max_cost=total_cost_cap,
            )
            est_tokens += counts["est_tokens"]
            label = "would embed" if args.dry_run else "embedded"
            print(
                f"{uid}: {label} {counts['digest']} digests, "
                f"{counts['news']} news, {counts['chat']} chats"
                + (f" (~{counts['est_tokens']} tokens)" if args.dry_run else "")
            )
        if args.dry_run:
            from app.config import embedding_price_for

            est = est_tokens * embedding_price_for(settings.embedding_model) / 1_000_000
            print(f"estimated cost: ~${est:.5f}")
        else:
            print(f"total embedding cost: ${client.cost_usd:.5f}")
    finally:
        await repo.dispose()


if __name__ == "__main__":
    asyncio.run(main())
