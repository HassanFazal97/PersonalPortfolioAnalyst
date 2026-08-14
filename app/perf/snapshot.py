"""Per-user dashboard snapshot cache with stale-while-revalidate.

The bootstrap endpoint serves the last built copy of each dashboard section
instantly and rebuilds expired sections in the background (single-flight per
user+section), so a warm GET never waits on yfinance, SnapTrade, or more
than the auth round-trip.

Two backends behind one async interface:

- ``SnapshotStore`` — in-process dicts, the default. Correct for exactly one
  web process.
- ``RedisSnapshotStore`` — shared cache for multi-worker deployments
  (REDIS_URL set): hits, invalidations, and the active-user set are shared
  across workers, and a cross-worker lock keeps rebuilds single-flight.

``configure(redis_url)`` in the app lifespan picks the backend; call sites
always go through ``snapshot.store``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from time import time as walltime
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
    """In-process backend (single web process)."""

    def __init__(self, max_users: int = 500) -> None:
        self._snaps: OrderedDict[uuid.UUID, dict[str, _Section]] = OrderedDict()
        self._inflight: dict[tuple[uuid.UUID, str], asyncio.Task] = {}
        self._last_seen: dict[uuid.UUID, float] = {}
        self._max_users = max_users

    # -- activity tracking (drives the warming jobs) -----------------------

    async def touch(self, user_id: uuid.UUID) -> None:
        self._last_seen[user_id] = monotonic()

    async def active_users(self, within_seconds: float) -> list[uuid.UUID]:
        cutoff = monotonic() - within_seconds
        return [u for u, t in self._last_seen.items() if t >= cutoff]

    # -- read/write ---------------------------------------------------------

    async def get(self, user_id: uuid.UUID) -> tuple[dict[str, Any], list[str]]:
        """(sections present, names past their TTL). Missing sections are the
        caller's to build inline; stale ones to refresh in background."""
        snap = self._snaps.get(user_id)
        if snap is None:
            return {}, []
        self._snaps.move_to_end(user_id)
        now = monotonic()
        stale = [n for n, sec in snap.items() if now - sec.built_at > section_ttl(n)]
        return {n: sec.data for n, sec in snap.items()}, stale

    async def put(self, user_id: uuid.UUID, name: str, data: Any) -> None:
        snap = self._snaps.setdefault(user_id, {})
        snap[name] = _Section(data=data, built_at=monotonic())
        self._snaps.move_to_end(user_id)
        while len(self._snaps) > self._max_users:
            evicted, _ = self._snaps.popitem(last=False)
            self._last_seen.pop(evicted, None)

    async def invalidate(self, user_id: uuid.UUID, *names: str) -> None:
        """Drop sections after a write (all of the user's when no names)."""
        snap = self._snaps.get(user_id)
        if snap is None:
            return
        if not names:
            self._snaps.pop(user_id, None)
            return
        for n in names:
            snap.pop(n, None)

    async def clear(self) -> None:
        """Global reset — after jobs that rewrite data for every user."""
        self._snaps.clear()

    async def close(self) -> None:  # interface parity with the Redis backend
        return None

    # -- background refresh ---------------------------------------------------

    async def refresh(
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
        await self.put(user_id, name, data)


class RedisSnapshotStore:
    """Shared backend for multi-worker deployments.

    Sections live at ``snap:{version}:{user}:{section}`` as JSON
    ``{"d": data, "t": wall_built_at}``. ``clear()`` bumps the version key
    so old entries orphan instantly (each key carries a hard EXPIRE backstop,
    so orphans purge themselves). Activity is a shared ZSET; rebuild
    single-flight is a local in-flight map plus a cross-worker ``SET NX``
    lock. Timestamps are wall-clock — monotonic clocks don't compare across
    processes."""

    # Hard Redis expiry backstop: comfortably above every logical TTL.
    _HARD_EXPIRE_SECONDS = 3600
    _LOCK_EXPIRE_SECONDS = 60

    def __init__(self, url: str, *, client: Any = None) -> None:
        if client is None:
            import redis.asyncio as aioredis

            client = aioredis.from_url(url, decode_responses=True)
        self._r = client
        self._inflight: dict[tuple[uuid.UUID, str], asyncio.Task] = {}

    async def _version(self) -> str:
        ver = await self._r.get("snap:ver")
        return ver or "0"

    def _key(self, ver: str, user_id: uuid.UUID, name: str) -> str:
        return f"snap:{ver}:{user_id}:{name}"

    # -- activity tracking ---------------------------------------------------

    async def touch(self, user_id: uuid.UUID) -> None:
        try:
            await self._r.zadd("snap:active", {str(user_id): walltime()})
        except Exception as exc:  # noqa: BLE001 - cache must never 500 a request
            _log.warning("snapshot touch failed: %s", exc)

    async def active_users(self, within_seconds: float) -> list[uuid.UUID]:
        try:
            raw = await self._r.zrangebyscore(
                "snap:active", walltime() - within_seconds, "+inf"
            )
            return [uuid.UUID(v) for v in raw]
        except Exception as exc:  # noqa: BLE001
            _log.warning("snapshot active_users failed: %s", exc)
            return []

    # -- read/write ----------------------------------------------------------

    async def get(self, user_id: uuid.UUID) -> tuple[dict[str, Any], list[str]]:
        try:
            ver = await self._version()
            keys = [self._key(ver, user_id, n) for n in SECTION_NAMES]
            raws = await self._r.mget(keys)
        except Exception as exc:  # noqa: BLE001 - degrade to a cache miss
            _log.warning("snapshot get failed: %s", exc)
            return {}, []
        sections: dict[str, Any] = {}
        stale: list[str] = []
        now = walltime()
        for name, raw in zip(SECTION_NAMES, raws):
            if raw is None:
                continue
            try:
                entry = json.loads(raw)
            except ValueError:
                continue
            sections[name] = entry.get("d")
            if now - float(entry.get("t", 0)) > section_ttl(name):
                stale.append(name)
        return sections, stale

    async def put(self, user_id: uuid.UUID, name: str, data: Any) -> None:
        try:
            ver = await self._version()
            await self._r.set(
                self._key(ver, user_id, name),
                json.dumps({"d": data, "t": walltime()}, default=str),
                ex=self._HARD_EXPIRE_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 - a failed put is a future miss
            _log.warning("snapshot put failed: %s", exc)

    async def invalidate(self, user_id: uuid.UUID, *names: str) -> None:
        try:
            ver = await self._version()
            targets = names or SECTION_NAMES
            await self._r.delete(*(self._key(ver, user_id, n) for n in targets))
        except Exception as exc:  # noqa: BLE001
            _log.warning("snapshot invalidate failed: %s", exc)

    async def clear(self) -> None:
        try:
            await self._r.incr("snap:ver")
        except Exception as exc:  # noqa: BLE001
            _log.warning("snapshot clear failed: %s", exc)

    async def close(self) -> None:
        try:
            await self._r.aclose()
        except Exception:  # noqa: BLE001 - shutdown best-effort
            pass

    # -- background refresh ----------------------------------------------------

    async def refresh(
        self, user_id: uuid.UUID, names: list[str], builder: SectionBuilder
    ) -> None:
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
        lock_key = f"snap:lock:{user_id}:{name}"
        try:
            # Cross-worker single-flight: first worker in wins, the rest skip
            # (they will serve the stale copy until the winner's put lands).
            if not await self._r.set(
                lock_key, "1", nx=True, ex=self._LOCK_EXPIRE_SECONDS
            ):
                return
        except Exception as exc:  # noqa: BLE001 - if Redis is down, don't rebuild-stampede
            _log.warning("snapshot lock failed: %s", exc)
            return
        try:
            data = await builder(user_id, name)
        except Exception as exc:
            _log.warning("snapshot rebuild %s %s failed: %s", user_id, name, exc)
            return
        finally:
            try:
                await self._r.delete(lock_key)
            except Exception:  # noqa: BLE001
                pass
        await self.put(user_id, name, data)


# Process-wide singleton: request handlers and lifespan jobs share it. The
# lifespan swaps in the Redis backend when REDIS_URL is configured.
store: SnapshotStore | RedisSnapshotStore = SnapshotStore()


def configure(redis_url: str) -> None:
    """Pick the backend for this process (called from the app lifespan)."""
    global store
    store = RedisSnapshotStore(redis_url) if redis_url else SnapshotStore()


def reset() -> None:
    """Synchronous fresh-store swap for app construction (tests build many
    apps; prod builds one, then the lifespan configure() picks the backend)."""
    global store
    store = SnapshotStore()
