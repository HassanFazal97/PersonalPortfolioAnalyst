"""The enqueue_outbound push fan-out.

This is the highest-consequence edit in the delivery path: the function is
deliberately designed to write a ``status='skipped'`` row rather than raise
when no channel resolves, so a bug here means *nobody gets their digest,
silently*. These tests pin the two properties that matter — the fan-out is
strictly additive, and it can never take the real message down with it.

Note on scope: the suite has no Postgres, so `FakeRepo` mirrors the real
repo's fan-out rather than exercising its SQL. The parity test at the bottom
is what stops the two drifting; the call-site tests exercise real code.
"""

import inspect
import uuid

import pytest

from app.db.repo import Repo
from tests.fakes import FakeRepo

TOKEN_A = "ExponentPushToken[aaaaaaaaaaaaaaaaaaaaaa]"
TOKEN_B = "ExponentPushToken[bbbbbbbbbbbbbbbbbbbbbb]"


async def _verified_email(repo: FakeRepo, uid) -> None:
    """A user whose preferred channel actually resolves, so the fan-out is
    tested alongside a real delivery row rather than a skipped one."""
    await repo.upsert_notification_channel(uid, channel="email", destination="a@b.co")
    await repo.mark_channel_verified(uid, "email")
    await repo.set_preferred_channel(uid, "email")


def _push_rows(repo: FakeRepo) -> list:
    return [m for m in repo._outbox.values() if m.channel == "push"]


def _real_rows(repo: FakeRepo) -> list:
    return [m for m in repo._outbox.values() if m.channel != "push"]


@pytest.mark.asyncio
async def test_push_is_additive_not_instead_of():
    """The whole design: the preferred-channel row is written exactly as it
    would be without push. If this inverts, users lose their digest."""
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    await _verified_email(repo, uid)
    await repo.upsert_push_device(uid, expo_token=TOKEN_A)

    await repo.enqueue_outbound("the digest", user_id=uid, kind="digest", push=True)

    real = _real_rows(repo)
    assert len(real) == 1
    assert real[0].channel == "email"
    assert real[0].body == "the digest"
    assert len(_push_rows(repo)) == 1


@pytest.mark.asyncio
async def test_no_devices_changes_nothing():
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    await _verified_email(repo, uid)

    await repo.enqueue_outbound("the digest", user_id=uid, kind="digest", push=True)

    assert len(_real_rows(repo)) == 1
    assert _push_rows(repo) == []


@pytest.mark.asyncio
async def test_push_still_sent_when_the_preferred_channel_is_skipped():
    """A user with no verified channel still gets the push pointer — the
    skipped row is about email, not about push."""
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)  # no preferred_channel
    await repo.upsert_push_device(uid, expo_token=TOKEN_A)

    await repo.enqueue_outbound("the digest", user_id=uid, kind="digest", push=True)

    real = _real_rows(repo)
    assert len(real) == 1
    assert len(_push_rows(repo)) == 1


@pytest.mark.asyncio
async def test_one_row_per_device():
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    await _verified_email(repo, uid)
    await repo.upsert_push_device(uid, expo_token=TOKEN_A)
    await repo.upsert_push_device(uid, expo_token=TOKEN_B)

    await repo.enqueue_outbound("the digest", user_id=uid, kind="digest", push=True)

    rows = _push_rows(repo)
    assert {r.destination for r in rows} == {TOKEN_A, TOKEN_B}


@pytest.mark.asyncio
async def test_kind_filter_respects_device_preferences():
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    await _verified_email(repo, uid)
    await repo.upsert_push_device(uid, expo_token=TOKEN_A, kinds=["digest"])
    await repo.upsert_push_device(uid, expo_token=TOKEN_B, kinds=["alert"])

    await repo.enqueue_outbound("morning", user_id=uid, kind="digest", push=True)

    rows = _push_rows(repo)
    assert [r.destination for r in rows] == [TOKEN_A]


@pytest.mark.asyncio
async def test_disabled_devices_are_skipped():
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    await _verified_email(repo, uid)
    await repo.upsert_push_device(uid, expo_token=TOKEN_A)
    await repo.disable_push_device(TOKEN_A)

    await repo.enqueue_outbound("the digest", user_id=uid, kind="digest", push=True)

    assert _push_rows(repo) == []
    assert len(_real_rows(repo)) == 1


@pytest.mark.asyncio
async def test_another_users_device_never_receives():
    repo = FakeRepo()
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    repo.seed_user(mine)
    repo.seed_user(theirs)
    await _verified_email(repo, mine)
    await repo.upsert_push_device(theirs, expo_token=TOKEN_B)

    await repo.enqueue_outbound("mine", user_id=mine, kind="digest", push=True)

    assert _push_rows(repo) == []


@pytest.mark.asyncio
async def test_a_shared_device_moves_between_accounts():
    """UNIQUE on the token alone, not (user, token): one phone must never
    deliver two accounts' notifications."""
    repo = FakeRepo()
    first, second = uuid.uuid4(), uuid.uuid4()
    repo.seed_user(first)
    repo.seed_user(second)

    await repo.upsert_push_device(first, expo_token=TOKEN_A)
    await repo.upsert_push_device(second, expo_token=TOKEN_A)

    assert await repo.list_push_devices(first) == []
    assert len(await repo.list_push_devices(second)) == 1


@pytest.mark.asyncio
async def test_reregistering_revives_a_disabled_device():
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    await repo.upsert_push_device(uid, expo_token=TOKEN_A)
    await repo.disable_push_device(TOKEN_A)

    await repo.upsert_push_device(uid, expo_token=TOKEN_A)

    assert len(await repo.list_push_devices(uid)) == 1


@pytest.mark.asyncio
async def test_push_body_is_truncated_to_a_pointer():
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    await repo.upsert_push_device(uid, expo_token=TOKEN_A)

    await repo.enqueue_outbound("x" * 4000, user_id=uid, kind="digest", push=True)

    assert len(_push_rows(repo)[0].body) <= 150


@pytest.mark.asyncio
async def test_deep_link_and_title_ride_in_the_payload():
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    await repo.upsert_push_device(uid, expo_token=TOKEN_A)

    await repo.enqueue_outbound(
        "body",
        user_id=uid,
        kind="digest",
        push=True,
        push_title="Your morning digest",
        deep_link="cirvia://digest",
    )

    payload = _push_rows(repo)[0].payload
    assert payload["title"] == "Your morning digest"
    assert payload["deep_link"] == "cirvia://digest"
    assert payload["kind"] == "digest"


@pytest.mark.asyncio
async def test_push_defaults_to_off():
    """Every existing call site that does not opt in must be unchanged."""
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    await repo.upsert_push_device(uid, expo_token=TOKEN_A)

    await repo.enqueue_outbound("no push please", user_id=uid, kind="digest")

    assert _push_rows(repo) == []


def test_fake_and_real_enqueue_signatures_match():
    """The fake mirrors the real fan-out rather than exercising it, so the one
    thing that must not drift is the contract between them. A new kwarg on the
    real repo that the fake lacks would make every push test a false pass."""
    real = inspect.signature(Repo.enqueue_outbound).parameters
    fake = inspect.signature(FakeRepo.enqueue_outbound).parameters
    assert set(real) == set(fake)
    for name, param in real.items():
        if name in ("self", "body"):
            continue
        assert fake[name].default == param.default, name


def test_fake_implements_every_new_device_method():
    for name in (
        "upsert_push_device",
        "list_push_devices",
        "disable_push_device",
        "set_push_device_kinds",
    ):
        assert hasattr(FakeRepo, name), f"FakeRepo is missing {name}"
        assert set(inspect.signature(getattr(Repo, name)).parameters) == set(
            inspect.signature(getattr(FakeRepo, name)).parameters
        ), name
