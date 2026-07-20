import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

import app.main as main
from app.config import get_settings
from tests.fakes import FakeRepo


def _seed_chat_runs(repo, uid, n, *, age=timedelta(hours=1), status="completed"):
    """Insert n chat runs created ``age`` ago for the quota counter to find."""
    stamp = datetime.now(timezone.utc) - age
    for _ in range(n):
        run_id = uuid.uuid4()
        repo.runs[run_id] = {
            "trigger": "chat",
            "user_id": uid,
            "status": status,
            "created_at": stamp,
        }


async def test_free_user_under_quota_passes():
    repo = FakeRepo()
    settings = get_settings()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    _seed_chat_runs(repo, uid, settings.free_weekly_chat_limit - 1)
    await main._enforce_usage_limits(repo, uid, settings)


async def test_free_user_weekly_quota_blocks_with_reset_date():
    repo = FakeRepo()
    settings = get_settings()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    _seed_chat_runs(repo, uid, settings.free_weekly_chat_limit, age=timedelta(days=2))
    with pytest.raises(HTTPException) as exc:
        await main._enforce_usage_limits(repo, uid, settings)
    assert exc.value.status_code == 402
    detail = exc.value.detail
    assert "free questions this week" in detail
    assert "Upgrade to Pro" in detail
    # A concrete unlock date (oldest question + 7 days) is part of the copy.
    assert "question unlocks" in detail


async def test_free_quota_is_rolling_seven_days():
    repo = FakeRepo()
    settings = get_settings()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    # Questions older than the rolling window don't count.
    _seed_chat_runs(repo, uid, settings.free_weekly_chat_limit, age=timedelta(days=8))
    await main._enforce_usage_limits(repo, uid, settings)


async def test_error_runs_do_not_burn_quota():
    repo = FakeRepo()
    settings = get_settings()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    _seed_chat_runs(repo, uid, settings.free_weekly_chat_limit, status="error")
    await main._enforce_usage_limits(repo, uid, settings)


async def test_pro_user_daily_quota():
    repo = FakeRepo()
    settings = get_settings()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")

    _seed_chat_runs(repo, uid, settings.pro_daily_chat_limit - 1)
    await main._enforce_usage_limits(repo, uid, settings)

    _seed_chat_runs(repo, uid, 1)
    with pytest.raises(HTTPException) as exc:
        await main._enforce_usage_limits(repo, uid, settings)
    assert exc.value.status_code == 402
    assert "questions per day on Pro" in exc.value.detail
    assert "unlocks at" in exc.value.detail


async def test_pro_quota_is_rolling_24_hours_not_weekly():
    repo = FakeRepo()
    settings = get_settings()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    # A heavy week doesn't cap Pro as long as the last 24h are under the limit.
    _seed_chat_runs(repo, uid, 50, age=timedelta(days=3))
    _seed_chat_runs(repo, uid, settings.pro_daily_chat_limit - 1)
    await main._enforce_usage_limits(repo, uid, settings)


async def test_monthly_cost_cap_still_backstops_both_plans():
    settings = get_settings()
    for plan, cap in (
        ("free", settings.free_monthly_cost_cap_usd),
        ("pro", settings.pro_monthly_cost_cap_usd),
    ):
        repo = FakeRepo()
        uid = uuid.uuid4()
        repo.seed_user(uid, plan=plan)
        repo._cost_override[uid] = cap + 0.01
        with pytest.raises(HTTPException) as exc:
            await main._enforce_usage_limits(repo, uid, settings)
        assert exc.value.status_code == 402
        assert "compute cap" in exc.value.detail


async def test_owner_is_exempt_from_limits():
    repo = FakeRepo()
    settings = get_settings()
    # Owner has no seeded user row and no caps apply.
    await main._enforce_usage_limits(repo, main._OWNER_USER_ID, settings)
