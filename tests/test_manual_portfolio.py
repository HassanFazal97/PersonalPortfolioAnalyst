"""POST /portfolio/manual — the no-brokerage onboarding fallback."""

import uuid

from fastapi.testclient import TestClient

import app.main as main
from app.config import get_settings
from app.main import create_app
from tests.fakes import FakeRepo

_AUTH = {"Authorization": "Bearer test-token"}


def _client(monkeypatch, repo):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    get_settings.cache_clear()
    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.macro_scheduler = None
    return TestClient(app)


def _fake_quotes(monkeypatch, prices):
    async def fake(payload, ctx=None):
        return {
            "quotes": [
                {"ticker": t, "last_price": prices[t]}
                for t in payload["tickers"]
                if t in prices
            ],
            "errors": [],
        }

    monkeypatch.setattr(main.market, "get_quote", fake)


def test_manual_entry_creates_positions_and_arms_trial(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    client = _client(monkeypatch, repo)
    monkeypatch.setattr(main, "_user_id", lambda request: uid)
    _fake_quotes(monkeypatch, {"NVDA": 100.0, "RY.TO": 150.0})

    body = client.post(
        "/portfolio/manual",
        headers=_AUTH,
        json={
            "positions": [
                {"ticker": "NVDA", "quantity": 2},
                {"ticker": "nvda", "quantity": 1},  # dedupes + normalizes
                {"ticker": "RY.TO", "quantity": 5},
            ]
        },
    ).json()
    assert body["positions"] == 2
    assert "trial_ends_at" in body  # first value moment arms the trial
    assert (uid, "portfolio_connected") in repo.funnel_events

    rows = {(p.ticker, p.account): p for p in repo._position_rows.values()}
    assert rows[("NVDA", "Manual")].quantity == 3
    assert rows[("RY.TO", "Manual")].currency == "CAD"
    assert rows[("NVDA", "Manual")].currency == "USD"
    assert rows[("NVDA", "Manual")].avg_cost == 100.0


def test_manual_entry_replaces_manual_but_keeps_brokerage(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    client = _client(monkeypatch, repo)
    monkeypatch.setattr(main, "_user_id", lambda request: uid)
    _fake_quotes(monkeypatch, {"NVDA": 100.0, "SHOP.TO": 90.0})

    async def seed():
        await repo.upsert_position(
            ticker="TD.TO", quantity=1, avg_cost=80, currency="CAD",
            account="TFSA", user_id=uid,
        )
        await repo.upsert_position(
            ticker="NVDA", quantity=1, avg_cost=90, currency="USD",
            account="Manual", user_id=uid,
        )

    import asyncio

    asyncio.run(seed())
    body = client.post(
        "/portfolio/manual",
        headers=_AUTH,
        json={"positions": [{"ticker": "SHOP.TO", "quantity": 2}]},
    ).json()
    assert body == {"positions": 1, "removed": 1, **{
        k: v for k, v in body.items() if k == "trial_ends_at"
    }}
    accounts = {(p.ticker, p.account) for p in repo._position_rows.values()}
    # The old manual NVDA row is gone; the brokerage TFSA row survives.
    assert accounts == {("SHOP.TO", "Manual"), ("TD.TO", "TFSA")}


def test_manual_entry_rejects_junk(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    client = _client(monkeypatch, repo)
    monkeypatch.setattr(main, "_user_id", lambda request: uid)
    _fake_quotes(monkeypatch, {"NVDA": 100.0})

    assert (
        client.post(
            "/portfolio/manual", headers=_AUTH, json={"positions": []}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/portfolio/manual",
            headers=_AUTH,
            json={"positions": [{"ticker": "NVDA", "quantity": -1}]},
        ).status_code
        == 400
    )
    resp = client.post(
        "/portfolio/manual",
        headers=_AUTH,
        json={"positions": [{"ticker": "ZZZJUNK", "quantity": 1}]},
    )
    assert resp.status_code == 404
    assert "ZZZJUNK" in resp.json()["detail"]
