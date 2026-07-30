"""Best Stocks API routes and the /app/picks page shell."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient

import app.main as main
from app.config import get_settings
from app.main import create_app
from app.webapp import picks_page
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


def _as_user(monkeypatch, uid):
    monkeypatch.setattr(main, "_user_id", lambda request: uid)


async def _seed_run(repo, *, run_date=None, payload=None, status="completed"):
    run_date = run_date or date.today()
    picks_run_id = await repo.create_picks_run(
        run_date=run_date, universe="sp500+tsx60"
    )
    await repo.update_picks_run(
        picks_run_id,
        status=status,
        payload=payload
        or {
            "as_of": run_date.isoformat(),
            "picks": [{"ticker": "CHEAP", "rank": 1}],
            "movers": [],
            "disclaimer": "test",
        },
    )
    return picks_run_id


def test_picks_requires_auth(monkeypatch):
    client = _client(monkeypatch, FakeRepo())
    assert client.get("/stocks/picks").status_code == 401


def test_picks_owner_sees_latest_run(monkeypatch):
    repo = FakeRepo()
    client = _client(monkeypatch, repo)
    asyncio.run(_seed_run(repo))
    resp = client.get("/stocks/picks", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["picks"][0]["ticker"] == "CHEAP"
    assert "stale" not in body


def test_picks_empty_state(monkeypatch):
    client = _client(monkeypatch, FakeRepo())
    resp = client.get("/stocks/picks", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["note"]


def test_picks_free_user_gets_402(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    asyncio.run(_seed_run(repo))
    assert client.get("/stocks/picks", headers=_AUTH).status_code == 402
    # The track record is the public proof surface — open to free users and
    # even unauthenticated visitors (the marketing site links to it).
    assert (
        client.get("/stocks/picks/track-record", headers=_AUTH).status_code == 200
    )
    assert client.get("/stocks/picks/track-record").status_code == 200


def test_picks_pro_user_ok(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    asyncio.run(_seed_run(repo))
    body = client.get("/stocks/picks", headers=_AUTH).json()
    assert body["available"] is True


def test_picks_stale_note(monkeypatch):
    repo = FakeRepo()
    client = _client(monkeypatch, repo)
    old = date.today() - timedelta(days=10)
    asyncio.run(_seed_run(repo, run_date=old))
    body = client.get("/stocks/picks", headers=_AUTH).json()
    assert body["stale"] is True
    assert old.isoformat() in body["stale_note"]


def test_track_record_computed_at_read_time(monkeypatch):
    repo = FakeRepo()
    client = _client(monkeypatch, repo)

    async def seed():
        run_date = date.today() - timedelta(days=30)
        picks_run_id = await _seed_run(repo, run_date=run_date)
        await repo.insert_pick_entries(
            [
                {
                    "picks_run_id": picks_run_id,
                    "run_date": run_date,
                    "ticker": "CHEAP",
                    "rank": 1,
                    "composite_score": 0.5,
                    "confidence": 0.7,
                    "entry_price": 100.0,
                    "factors": {},
                    "thesis_summary": "t",
                }
            ]
        )
        # entry_price is frozen from the last close BEFORE the pre-market
        # run, so the measured span starts at the prior day's bar. Returns
        # come from the stored series itself (same-series adjusted ratio),
        # not the frozen dollar figure. Pick since then: +10%; SPY (the
        # total-return benchmark) over the identical span: +2%.
        prior = run_date - timedelta(days=1)
        await repo.upsert_daily_prices(
            "CHEAP",
            [
                {"date": prior.isoformat(), "adj_close": 100.0},
                {"date": date.today().isoformat(), "adj_close": 110.0},
            ],
        )
        await repo.upsert_daily_prices(
            "SPY",
            [
                {"date": prior.isoformat(), "adj_close": 500.0},
                {"date": date.today().isoformat(), "adj_close": 510.0},
            ],
        )

    asyncio.run(seed())
    body = client.get("/stocks/picks/track-record", headers=_AUTH).json()
    assert body["available"] is True
    entry = body["entries"][0]
    assert entry["return_pct"] == 10.0
    assert entry["benchmark_return_pct"] == 2.0
    s = body["summary"]
    assert s["measured"] == 1
    assert s["beat_benchmark"] == 1
    assert s["hit_rate_pct"] == 100.0


def test_track_record_survives_series_readjustment(monkeypatch):
    """A 2:1 split after publication halves every stored historical close on
    the next full refetch. entry_price stays frozen in pre-split dollars for
    display, but the return must come from the re-adjusted series itself —
    scoring the new series against the frozen dollar figure would report a
    fake −45% on a pick that actually gained 10%."""
    repo = FakeRepo()
    client = _client(monkeypatch, repo)

    async def seed():
        run_date = date.today() - timedelta(days=30)
        picks_run_id = await _seed_run(repo, run_date=run_date)
        await repo.insert_pick_entries(
            [
                {
                    "picks_run_id": picks_run_id,
                    "run_date": run_date,
                    "ticker": "SPLIT",
                    "rank": 1,
                    "composite_score": 0.5,
                    "confidence": 0.7,
                    "entry_price": 100.0,  # frozen pre-split
                    "factors": {},
                    "thesis_summary": "t",
                }
            ]
        )
        prior = run_date - timedelta(days=1)
        # Post-split refetch: history re-adjusted to half the frozen price.
        await repo.upsert_daily_prices(
            "SPLIT",
            [
                {"date": prior.isoformat(), "adj_close": 50.0},
                {"date": date.today().isoformat(), "adj_close": 55.0},
            ],
        )
        await repo.upsert_daily_prices(
            "SPY",
            [
                {"date": prior.isoformat(), "adj_close": 500.0},
                {"date": date.today().isoformat(), "adj_close": 500.0},
            ],
        )

    asyncio.run(seed())
    entry = client.get("/stocks/picks/track-record", headers=_AUTH).json()["entries"][0]
    assert entry["entry_price"] == 100.0
    assert entry["return_pct"] == 10.0


def test_track_record_empty(monkeypatch):
    client = _client(monkeypatch, FakeRepo())
    body = client.get("/stocks/picks/track-record", headers=_AUTH).json()
    assert body["available"] is False


def test_manual_triggers_require_auth_and_owner(monkeypatch):
    repo = FakeRepo()
    client = _client(monkeypatch, repo)
    assert client.post("/stocks/picks/run").status_code == 401
    assert client.post("/stocks/picks/sync").status_code == 401
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    _as_user(monkeypatch, uid)
    assert client.post("/stocks/picks/run", headers=_AUTH).status_code == 403
    assert client.post("/stocks/picks/sync", headers=_AUTH).status_code == 403


def test_picks_page_renders():
    html = picks_page("https://x.supabase.co", "anon-key")
    assert "<title>Top Picks" in html
    assert "/stocks/picks" in html
    for token in (
        "picks-gate", "pickCard", "renderMovers", "loadTrackRecord",
        "picks-disclaimer", "How this is built", "confMeter",
    ):
        assert token in html
    # Design tokens only — no phantom vars.
    assert "var(--text)" not in html
    assert "var(--muted)" not in html
