"""Unit tests: app/perf/snapshot.py store semantics + app/perf/authcache.py."""

import asyncio
import uuid
from time import time as now

from app.perf import authcache
from app.perf.snapshot import SnapshotStore, section_ttl

U1 = uuid.uuid4()
U2 = uuid.uuid4()


# ---- SnapshotStore -----------------------------------------------------------


async def test_get_empty():
    assert await SnapshotStore().get(U1) == ({}, [])


async def test_put_and_get_fresh():
    store = SnapshotStore()
    await store.put(U1, "me", {"plan": "pro"})
    snap, stale = await store.get(U1)
    assert snap == {"me": {"plan": "pro"}}
    assert stale == []


async def test_stale_detection(monkeypatch):
    store = SnapshotStore()
    await store.put(U1, "me", {"plan": "pro"})
    # Age the section past its TTL by rewinding its built_at stamp.
    store._snaps[U1]["me"].built_at -= section_ttl("me") + 1
    snap, stale = await store.get(U1)
    assert snap == {"me": {"plan": "pro"}}  # stale data still served
    assert stale == ["me"]


async def test_invalidate_named_and_all():
    store = SnapshotStore()
    await store.put(U1, "me", 1)
    await store.put(U1, "news", 2)
    await store.invalidate(U1, "me")
    assert (await store.get(U1))[0] == {"news": 2}
    await store.invalidate(U1)
    assert await store.get(U1) == ({}, [])


async def test_lru_eviction():
    store = SnapshotStore(max_users=2)
    u3 = uuid.uuid4()
    await store.put(U1, "me", 1)
    await store.put(U2, "me", 2)
    await store.put(u3, "me", 3)
    assert await store.get(U1) == ({}, [])  # oldest evicted
    assert (await store.get(U2))[0] == {"me": 2}


async def test_active_users_tracking():
    store = SnapshotStore()
    await store.touch(U1)
    assert U1 in await store.active_users(60)
    assert await store.active_users(0) == []


async def test_refresh_single_flight_and_serve_stale_on_failure():
    store = SnapshotStore()
    await store.put(U1, "portfolio", {"positions": ["old"]})
    calls = 0
    gate: asyncio.Future = asyncio.get_event_loop().create_future()

    async def builder(user_id, name):
        nonlocal calls
        calls += 1
        await gate
        raise RuntimeError("rebuild failed")

    await store.refresh(U1, ["portfolio"], builder)
    await store.refresh(U1, ["portfolio"], builder)  # coalesced: still in flight
    await asyncio.sleep(0)
    gate.set_result(None)
    await asyncio.gather(*store._inflight.values(), return_exceptions=True)
    assert calls == 1
    # Failed rebuild keeps the previous copy (serve-stale over error).
    assert (await store.get(U1))[0] == {"portfolio": {"positions": ["old"]}}


async def test_refresh_success_replaces_data():
    store = SnapshotStore()
    await store.put(U1, "news", {"items": []})

    async def builder(user_id, name):
        return {"items": ["fresh"]}

    await store.refresh(U1, ["news"], builder)
    await asyncio.gather(*store._inflight.values(), return_exceptions=True)
    assert (await store.get(U1))[0] == {"news": {"items": ["fresh"]}}


# ---- authcache ---------------------------------------------------------------


def test_user_id_roundtrip_and_evict():
    authcache.cache_clear()
    auth_id, user_id = uuid.uuid4(), uuid.uuid4()
    assert authcache.get_user_id(auth_id) is None
    authcache.put_user_id(auth_id, user_id)
    assert authcache.get_user_id(auth_id) == user_id
    authcache.evict_user(auth_id)
    assert authcache.get_user_id(auth_id) is None
    authcache.evict_user(None)  # tolerated


def test_verified_token_respects_exp():
    authcache.cache_clear()
    auth_id = uuid.uuid4()
    authcache.put_verified("tok-live", auth_id, "a@b.c", now() + 60)
    assert authcache.get_verified("tok-live") == (auth_id, "a@b.c")
    authcache.put_verified("tok-dead", auth_id, None, now() - 1)
    assert authcache.get_verified("tok-dead") is None
    assert authcache.get_verified("tok-unknown") is None
