"""RedisSnapshotStore semantics against fakeredis — put/get TTL staleness,
invalidation, the version-bump clear, cross-worker single-flight, and
degrade-to-miss when Redis is unreachable."""

import asyncio
import json
import uuid
from time import time as now

import fakeredis.aioredis

from app.perf.snapshot import RedisSnapshotStore, SnapshotStore, section_ttl

U1 = uuid.uuid4()
U2 = uuid.uuid4()


def _store() -> RedisSnapshotStore:
    return RedisSnapshotStore("redis://unused", client=fakeredis.aioredis.FakeRedis(decode_responses=True))


async def test_put_get_roundtrip_and_missing():
    store = _store()
    assert await store.get(U1) == ({}, [])
    await store.put(U1, "me", {"plan": "pro"})
    snap, stale = await store.get(U1)
    assert snap == {"me": {"plan": "pro"}}
    assert stale == []


async def test_stale_detection_by_wall_clock():
    store = _store()
    await store.put(U1, "me", {"plan": "pro"})
    # Rewind the stored built_at past the section TTL.
    ver = await store._version()
    key = store._key(ver, U1, "me")
    entry = json.loads(await store._r.get(key))
    entry["t"] = now() - section_ttl("me") - 1
    await store._r.set(key, json.dumps(entry))
    snap, stale = await store.get(U1)
    assert snap == {"me": {"plan": "pro"}}  # stale data still served
    assert stale == ["me"]


async def test_invalidate_named_and_all():
    store = _store()
    await store.put(U1, "me", 1)
    await store.put(U1, "news", 2)
    await store.invalidate(U1, "me")
    assert (await store.get(U1))[0] == {"news": 2}
    await store.invalidate(U1)
    assert await store.get(U1) == ({}, [])


async def test_clear_bumps_version_for_all_users():
    store = _store()
    await store.put(U1, "me", 1)
    await store.put(U2, "me", 2)
    await store.clear()
    assert await store.get(U1) == ({}, [])
    assert await store.get(U2) == ({}, [])
    # And a fresh put after the bump works normally.
    await store.put(U1, "me", 3)
    assert (await store.get(U1))[0] == {"me": 3}


async def test_active_users_shared_zset():
    store = _store()
    await store.touch(U1)
    assert U1 in await store.active_users(60)
    assert await store.active_users(0) == []


async def test_refresh_single_flight_via_lock():
    # Two stores sharing one fake server = two workers sharing Redis.
    server = fakeredis.FakeServer()
    s1 = RedisSnapshotStore(
        "redis://unused",
        client=fakeredis.aioredis.FakeRedis(server=server, decode_responses=True),
    )
    s2 = RedisSnapshotStore(
        "redis://unused",
        client=fakeredis.aioredis.FakeRedis(server=server, decode_responses=True),
    )
    calls = 0
    gate: asyncio.Future = asyncio.get_event_loop().create_future()

    async def builder(user_id, name):
        nonlocal calls
        calls += 1
        await gate
        return {"fresh": True}

    await s1.refresh(U1, ["news"], builder)
    await asyncio.sleep(0.01)  # let worker 1 grab the lock
    await s2.refresh(U1, ["news"], builder)  # other worker: lock held, skips
    gate.set_result(None)
    await asyncio.gather(
        *s1._inflight.values(), *s2._inflight.values(), return_exceptions=True
    )
    assert calls == 1
    assert (await s1.get(U1))[0] == {"news": {"fresh": True}}
    # Lock released after the rebuild, so a later refresh can run.
    assert await s1._r.get(f"snap:lock:{U1}:news") is None


async def test_redis_failure_degrades_to_miss():
    class Boom:
        def __getattr__(self, name):
            async def _fail(*a, **k):
                raise ConnectionError("redis down")

            return _fail

    store = RedisSnapshotStore("redis://unused", client=Boom())
    assert await store.get(U1) == ({}, [])  # miss, not a 500
    await store.put(U1, "me", 1)  # swallowed
    await store.invalidate(U1)  # swallowed
    await store.touch(U1)  # swallowed
    assert await store.active_users(60) == []


async def test_dict_and_redis_backends_agree_on_shape():
    for store in (SnapshotStore(), _store()):
        await store.put(U1, "digest", {"body": "hello"})
        snap, stale = await store.get(U1)
        assert snap == {"digest": {"body": "hello"}}
        assert stale == []
