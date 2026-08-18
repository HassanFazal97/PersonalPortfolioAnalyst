"""Thin HTTP client for the Senate/House Stock Watcher datasets.

Both are unofficial, community-maintained JSON mirrors of the Senate eFD /
House Clerk periodic transaction reports (there is no free structured
official source — the real disclosures are scanned PDFs). Each dataset is a
single flat JSON array with no pagination; "incremental" here means "cheap to
re-fetch and diff," not "fetch only new bytes" (see sync.py).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


async def fetch_transactions(url: str, *, settings: Settings) -> list[dict[str, Any]]:
    """Fetch and parse a Stock Watcher JSON dump. Returns [] on any failure —
    callers (sync.py) treat an empty result as "nothing new this run", never
    as a reason to wipe existing rows."""
    if not url:
        return []
    headers = {"User-Agent": settings.sec_edgar_user_agent}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=headers) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception:  # noqa: BLE001 - the caller fails open per source
        logger.warning("Stock Watcher fetch failed: %s", url, exc_info=True)
        return []
    if not isinstance(data, list):
        logger.warning("Stock Watcher response was not a list: %s", url)
        return []
    return [row for row in data if isinstance(row, dict)]
