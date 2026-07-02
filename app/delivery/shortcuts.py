"""Phase A delivery: the pull endpoint's data shape.

The iPhone Shortcut fetches ``GET /digest/latest`` each morning. This helper
returns today's digest (America/Toronto) or None if it hasn't been generated.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.db.repo import Repo


async def get_latest_digest(repo: Repo, *, tz: str) -> dict[str, Any] | None:
    today = datetime.now(ZoneInfo(tz)).date()
    digest = await repo.get_digest(today)
    if digest is None:
        return None
    return {
        "date": today.isoformat(),
        "body": digest.body,
        "generated_at": digest.created_at.isoformat() if digest.created_at else None,
    }
