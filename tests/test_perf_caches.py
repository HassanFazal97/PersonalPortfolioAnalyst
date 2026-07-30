"""Unit tests: app/perf/snapshot.py store semantics + app/perf/authcache.py."""

import asyncio
import uuid
from time import time as now

from app.perf import authcache
from app.perf.snapshot import SnapshotStore, section_ttl

U1 = uuid.uuid4()
U2 = uuid.uuid4()


# ---- SnapshotStore -----------------------------------------------------------


def test_get_empty():
    assert SnapshotStore().get(U1) == ({}, [])


def test_put_and_get_fresh():
    store = SnapshotStore()
    store.put(U1, "me", {"plan": "pro"})
    snap, stale = store.get(U1)
    assert snap == {"me": {"plan": "pro"}}
    assert stale == []


def test_stale_detection(monkeypatch):
    store = SnapshotStore()
    store.put(U1, "me", {"plan": "pro"})
    # Age the section past its TTL by rewinding its built_at stamp.
    store._snaps[U1]["me"].built_at -= section_ttl("me") + 1
    snap, stale = store.get(U1)
    assert snap == {"me": {"plan": "pro"}}  # stale data still served
    assert stale == ["me"]


def test_invalidate_named_and_all():
    store = SnapshotStore()
    store.put(U1, "me", 1)
    store.put(U1, "news", 2)
    store.invalidate(U1, "me")
    assert store.get(U1)[0] == {"news": 2}
    store.invalidate(U1)
    assert store.get(U1) == ({}, [])


def test_lru_eviction():
    store = SnapshotStore(max_users=2)
    u3 = uuid.uuid4()
    store.put(U1, "me", 1)
    store.put(U2, "me", 2)
    store.put(u3, "me", 3)
    assert store.get(U1) == ({}, [])  # oldest evicted
    assert store.get(U2)[0] == {"me": 2}


def test_active_users_tracking():
    store = SnapshotStore()
    store.touch(U1)
    assert U1 in store.active_users(60)
    assert store.active_users(0) == []


def test_refresh_single_flight_and_serve_stale_on_failure():
    async def run():
        store = SnapshotStore()
        store.put(U1, "portfolio", {"positions": ["old"]})
        calls = 0
        gate: asyncio.Future = asyncio.get_event_loop().create_future()

        async def builder(user_id, name):
            nonlocal calls
            calls += 1
            await gate
            raise RuntimeError("rebuild failed")

        store.refresh(U1, ["portfolio"], builder)
        store.refresh(U1, ["portfolio"], builder)  # coalesced: still in flight
        await asyncio.sleep(0)
        gate.set_result(None)
        await asyncio.gather(*store._inflight.values(), return_exceptions=True)
        assert calls == 1
        # Failed rebuild keeps the previous copy (serve-stale over error).
        assert store.get(U1)[0] == {"portfolio": {"positions": ["old"]}}

    asyncio.run(run())


def test_refresh_success_replaces_data():
    async def run():
        store = SnapshotStore()
        store.put(U1, "news", {"items": []})

        async def builder(user_id, name):
            return {"items": ["fresh"]}

        store.refresh(U1, ["news"], builder)
        await asyncio.gather(*store._inflight.values(), return_exceptions=True)
        assert store.get(U1)[0] == {"news": {"items": ["fresh"]}}

    asyncio.run(run())


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
