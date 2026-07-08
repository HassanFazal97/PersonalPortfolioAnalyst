"""Plan cadence and per-user digest fan-out."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.agent.digest_pipeline import run_digest_pipeline, run_digests_for_all
from app.config import DEFAULT_USER_ID, get_settings
from app.plans import digest_cadence_due
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)


def test_digest_cadence_pro_weekday():
    assert digest_cadence_due("pro", date(2026, 7, 6)) is True  # Mon
    assert digest_cadence_due("pro", date(2026, 7, 10)) is True  # Fri
    assert digest_cadence_due("pro", date(2026, 7, 11)) is False  # Sat


def test_digest_cadence_free_monday_only():
    assert digest_cadence_due("free", date(2026, 7, 6)) is True  # Mon
    assert digest_cadence_due("free", date(2026, 7, 7)) is False  # Tue


@pytest.mark.asyncio
async def test_run_digest_skipped_on_cadence_for_free_tuesday(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    await repo.upsert_position(
        ticker="NVDA", quantity=1, avg_cost=1, currency="USD", account="TFSA", user_id=uid
    )

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            from datetime import datetime
            from zoneinfo import ZoneInfo

            return datetime(2026, 7, 7, 8, 0, tzinfo=ZoneInfo("America/Toronto"))

    monkeypatch.setattr("app.agent.digest_pipeline.datetime", FakeDatetime)

    result = await run_digest_pipeline(repo, user_id=uid)
    assert result["status"] == "skipped_cadence"


@pytest.mark.asyncio
async def test_run_digest_skipped_when_already_sent(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    await repo.upsert_position(
        ticker="NVDA", quantity=1, avg_cost=1, currency="USD", account="TFSA", user_id=uid
    )
    monday = date(2026, 7, 6)
    await repo.upsert_digest(
        run_id=uuid.uuid4(), body="existing", digest_date=monday, user_id=uid
    )

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            from datetime import datetime
            from zoneinfo import ZoneInfo

            return datetime(2026, 7, 6, 8, 0, tzinfo=ZoneInfo("America/Toronto"))

    monkeypatch.setattr("app.agent.digest_pipeline.datetime", FakeDatetime)

    result = await run_digest_pipeline(repo, user_id=uid)
    assert result["status"] == "skipped_exists"


@pytest.mark.asyncio
async def test_run_digest_skipped_cost_cap(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    await repo.upsert_position(
        ticker="NVDA", quantity=1, avg_cost=1, currency="USD", account="TFSA", user_id=uid
    )
    settings = get_settings()
    repo._cost_override[uid] = settings.free_monthly_cost_cap_usd + 0.01

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            from datetime import datetime
            from zoneinfo import ZoneInfo

            return datetime(2026, 7, 6, 8, 0, tzinfo=ZoneInfo("America/Toronto"))

    monkeypatch.setattr("app.agent.digest_pipeline.datetime", FakeDatetime)

    result = await run_digest_pipeline(repo, user_id=uid)
    assert result["status"] == "skipped_cost_cap"


@pytest.mark.asyncio
async def test_run_digests_for_all_fan_out(monkeypatch):
    repo = FakeRepo()
    u_free = uuid.uuid4()
    u_pro = uuid.uuid4()
    repo.seed_user(u_free, plan="free")
    repo.seed_user(u_pro, plan="pro")
    for uid in (u_free, u_pro):
        await repo.upsert_position(
            ticker="NVDA", quantity=1, avg_cost=1, currency="USD",
            account="TFSA", user_id=uid,
        )

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            from datetime import datetime
            from zoneinfo import ZoneInfo

            return datetime(2026, 7, 6, 8, 0, tzinfo=ZoneInfo("America/Toronto"))

    monkeypatch.setattr("app.agent.digest_pipeline.datetime", FakeDatetime)
    monkeypatch.setattr(
        "app.agent.digest_pipeline.run_digest_pipeline",
        AsyncMock(side_effect=lambda db, *, user_id, client=None, force=False: {
            "user_id": str(user_id),
            "status": "completed",
        }),
    )

    results = await run_digests_for_all(repo)
    assert len(results) == 2
    ids = {r["user_id"] for r in results}
    assert str(u_free) in ids and str(u_pro) in ids


@pytest.mark.asyncio
async def test_free_plan_caps_holdings_in_market_context(monkeypatch):
    from app.agent import digest_pipeline as dp
    from app.tools.registry import ToolContext

    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    for i, ticker in enumerate(["AAA", "BBB", "CCC", "DDD"]):
        await repo.upsert_position(
            ticker=ticker, quantity=10 - i, avg_cost=1, currency="USD",
            account="TFSA", user_id=uid,
        )

    async def fake_get_portfolio(payload, ctx):
        positions = await ctx.repo.list_positions(user_id=ctx.user_id)
        return {
            "positions": [
                {"ticker": p.ticker, "quantity": float(p.quantity), "market_value": float(p.quantity) * 10}
                for p in positions
            ],
            "totals": {},
        }

    monkeypatch.setattr(dp.portfolio, "get_portfolio", fake_get_portfolio)
    monkeypatch.setattr(dp.market, "get_price_history", AsyncMock(return_value={"period_return_pct": 1.0}))

    ctx = ToolContext(settings=get_settings(), repo=repo, user_id=uid)
    raw = await dp.build_market_context(
        ctx, tz="America/Toronto", plan="free", digest_tickers=[]
    )
    import json

    data = json.loads(raw)
    assert len(data["positions"]) == 3
    assert data.get("holdings_capped") == 3
