import uuid

import pytest
from fastapi import HTTPException

import app.main as main
from app.config import get_settings
from tests.fakes import FakeRepo


async def test_enforce_usage_limits_free_user():
    repo = FakeRepo()
    settings = get_settings()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")

    # Under all limits — no raise.
    await main._enforce_usage_limits(repo, uid, settings)

    # Over the monthly cost cap → 402.
    repo._cost_override[uid] = 999.0
    with pytest.raises(HTTPException) as exc:
        await main._enforce_usage_limits(repo, uid, settings)
    assert exc.value.status_code == 402

    # Under cost, but at the Free daily chat cap → 402.
    repo._cost_override[uid] = 0.0
    repo._chats_override[uid] = settings.free_daily_chat_limit
    with pytest.raises(HTTPException):
        await main._enforce_usage_limits(repo, uid, settings)


async def test_pro_user_not_daily_capped_but_cost_capped():
    repo = FakeRepo()
    settings = get_settings()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")

    # A huge chat count doesn't cap Pro (only the cost ceiling does).
    repo._chats_override[uid] = 10_000
    await main._enforce_usage_limits(repo, uid, settings)

    repo._cost_override[uid] = settings.pro_monthly_cost_cap_usd + 1
    with pytest.raises(HTTPException):
        await main._enforce_usage_limits(repo, uid, settings)


async def test_owner_is_exempt_from_limits():
    repo = FakeRepo()
    settings = get_settings()
    # Owner has no seeded user row and no caps apply.
    await main._enforce_usage_limits(repo, main._OWNER_USER_ID, settings)
