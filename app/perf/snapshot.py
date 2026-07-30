"""Per-user dashboard snapshot cache with stale-while-revalidate.

The bootstrap endpoint serves the last built copy of each dashboard section
instantly and rebuilds expired sections in the background (single-flight per
user+section), so a warm GET never waits on yfinance, SnapTrade, or more
than the auth round-trip. In-process by design — same single-process
precedent as app/tools/market.py; swap the dict backend behind this same
interface when the deployment goes multi-process.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

_log = logging.getLogger(__name__)

SECTION_NAMES = (
    "me",
    "portfolio",
    "watchlist",
    "digest",
    "news",
    "status",
    "notifications",
)

# A builder takes (user_id, section_name) and returns the section's raw data.
SectionBuilder = Callable[[uuid.UUID, str], Awaitable[Any]]


def market_hours_now() -> bool:
    """Rough NYSE/TSX regular session (weekday 9:30–16:00 ET). Only widens a
    TTL, so holiday imprecision is harmless."""
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= minutes <= 16 * 60


def section_ttl(name: str) -> float:
    """Freshness window per section, in seconds."""
    if name == "portfolio":
        # Quotes move during the session; off-hours the close doesn't change.
        return 60.0 if market_hours_now() else 600.0
    if name in ("status", "notifications"):
        # Connection health / channel config change rarely, and their writes
        # invalidate explicitly.
        return 900.0
    # me, watchlist, digest, news: cheap DB reads, invalidation-driven.
    return 300.0


@dataclass
class _Section:
    data: Any
    built_at: float


class SnapshotStore:
    def __init__(self, max_users: int = 500) -> None:
        self._snaps: OrderedDict[uuid.UUID, dict[str, _Section]] = OrderedDict()
        self._inflight: dict[tuple[uuid.UUID, str], asyncio.Task] = {}
        self._last_seen: dict[uuid.UUID, float] = {}
        self._max_users = max_users

    # -- activity tracking (drives the warming jobs) -----------------------

    def touch(self, user_id: uuid.UUID) -> None:
        self._last_seen[user_id] = monotonic()

    def active_users(self, within_seconds: float) -> list[uuid.UUID]:
        cutoff = monotonic() - within_seconds
        return [u for u, t in self._last_seen.items() if t >= cutoff]

    # -- read/write ---------------------------------------------------------

    def get(self, user_id: uuid.UUID) -> tuple[dict[str, Any], list[str]]:
        """(sections present, names past their TTL). Missing sections are the
        caller's to build inline; stale ones to refresh in background."""
        snap = self._snaps.get(user_id)
        if snap is None:
            return {}, []
        self._snaps.move_to_end(user_id)
        now = monotonic()
        stale = [n for n, sec in snap.items() if now - sec.built_at > section_ttl(n)]
        return {n: sec.data for n, sec in snap.items()}, stale

    def put(self, user_id: uuid.UUID, name: str, data: Any) -> None:
        snap = self._snaps.setdefault(user_id, {})
        snap[name] = _Section(data=data, built_at=monotonic())
        self._snaps.move_to_end(user_id)
        while len(self._snaps) > self._max_users:
            evicted, _ = self._snaps.popitem(last=False)
            self._last_seen.pop(evicted, None)

    def invalidate(self, user_id: uuid.UUID, *names: str) -> None:
        """Drop sections after a write (all of the user's when no names)."""
        snap = self._snaps.get(user_id)
        if snap is None:
            return
        if not names:
            self._snaps.pop(user_id, None)
            return
        for n in names:
            snap.pop(n, None)

    def clear(self) -> None:
        """Global reset — after jobs that rewrite data for every user."""
        self._snaps.clear()

    # -- background refresh ---------------------------------------------------

    def refresh(
        self, user_id: uuid.UUID, names: list[str], builder: SectionBuilder
    ) -> None:
        """Fire-and-forget rebuild, single-flight per (user, section). A failed
        rebuild keeps the previous (stale) copy — serve-stale over error."""
        for name in names:
            key = (user_id, name)
            if key in self._inflight:
                continue
            task = asyncio.create_task(self._rebuild(user_id, name, builder))
            self._inflight[key] = task
            task.add_done_callback(lambda _t, k=key: self._inflight.pop(k, None))

    async def _rebuild(
        self, user_id: uuid.UUID, name: str, builder: SectionBuilder
    ) -> None:
        try:
            data = await builder(user_id, name)
        except Exception as exc:
            _log.warning("snapshot rebuild %s %s failed: %s", user_id, name, exc)
            return
        self.put(user_id, name, data)


# Process-wide singleton: request handlers and lifespan jobs share it.
store = SnapshotStore()
