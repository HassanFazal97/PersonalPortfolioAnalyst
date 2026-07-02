"""Phase B delivery: the outbound-message queue the Mac worker drains.

The API never sends iMessages itself. ``send_digest`` (and the digest fallback)
enqueue rows into ``outbound_messages``; the Mac-side worker polls
``GET /outbox/pending``, sends each via AppleScript, and acks back. This module
holds the queue-shaping helpers used by the outbox endpoints.
"""

from __future__ import annotations

from typing import Any

from app.db.repo import Repo

MAX_ATTEMPTS = 3


async def pending_payload(repo: Repo, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = await repo.pending_outbound(limit=limit)
    return [{"id": str(r.id), "body": r.body, "attempts": r.attempts or 0} for r in rows]
