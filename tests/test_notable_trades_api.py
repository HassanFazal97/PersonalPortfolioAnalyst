"""Notable Investor Trades API: public teaser, Pro gate (402), the gated
feed/summary/follow routes, and the relevance-to-holdings join — offline via
FakeRepo."""

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

import app.main as main
from app.config import DEFAULT_USER_ID, get_settings
from app.integrations.congress_trades.mapper import map_record
from app.main import create_app
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
_AUTH = {"Authorization": "Bearer test-token"}

_SENATE_ROW = {
    "senator": "Jane Smith",
    "state": "TX",
    "party": "R",
    "ticker": "NVDA",
    "asset_description": "NVIDIA Corp",
    "type": "Purchase",
    "amount": "$1,001 - $15,000",
    "transaction_date": "2026-08-01",
    "disclosure_date": "2026-08-10",
    "ptr_link": "https://example.com/senate.pdf",
}


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


async def _seed_one_trade(repo, **row_overrides):
    mapped = map_record(dict(_SENATE_ROW, **row_overrides), chamber="senate")
    investor, trade = mapped
    investor_id = await repo.upsert_congress_investor(investor)
    await repo.upsert_notable_investor_trade(investor_id=investor_id, trade=trade)
    return investor_id


async def test_teaser_is_public_and_never_empty_when_data_exists(monkeypatch):
    repo = FakeRepo()
    await _seed_one_trade(repo)
    client = _client(monkeypatch, repo)

    resp = client.get("/notable-trades/teaser")  # no Authorization header

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["ticker"] == "NVDA"
    assert data["items"][0]["investor"]["name"] == "Jane Smith"


async def test_feed_is_402_for_free_user(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    await _seed_one_trade(repo)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.get("/notable-trades", headers=_AUTH)

    assert resp.status_code == 402


async def test_feed_returns_trades_for_pro_user(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    await _seed_one_trade(repo)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.get("/notable-trades", headers=_AUTH)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["ticker"] == "NVDA"
    assert item["transaction_type"] == "buy"
    assert item["amount_range"] == "$1,001–$15,000"
    assert item["relevance"] == {"held": False, "watched": False}


async def test_feed_flags_relevance_to_held_ticker(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    await repo.upsert_position(
        ticker="NVDA", quantity=Decimal("5"), avg_cost=Decimal("100"),
        currency="USD", account="taxable", user_id=uid,
    )
    await _seed_one_trade(repo)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    data = client.get("/notable-trades", headers=_AUTH).json()

    assert data["items"][0]["relevance"]["held"] is True


async def test_feed_filters_by_ticker_and_side(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    await _seed_one_trade(repo)  # NVDA buy
    await _seed_one_trade(
        repo, ticker="AAPL", type="Sale (Full)", disclosure_date="2026-08-12",
        transaction_date="2026-08-03",
    )
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.get("/notable-trades?ticker=AAPL", headers=_AUTH).json()
    assert [i["ticker"] for i in resp["items"]] == ["AAPL"]

    resp = client.get("/notable-trades?side=sell", headers=_AUTH).json()
    assert [i["ticker"] for i in resp["items"]] == ["AAPL"]


async def test_ticker_summary_is_pro_gated_and_aggregates(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    await _seed_one_trade(repo)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    assert client.get("/notable-trades/tickers/NVDA/summary", headers=_AUTH).status_code == 402

    repo.seed_user(uid, plan="pro")
    data = client.get("/notable-trades/tickers/NVDA/summary", headers=_AUTH).json()
    assert data["buys"] == 1
    assert data["sells"] == 0
    assert data["distinct_investors"] == 1
    assert data["by_type"] == {"congress": 1}
    assert len(data["recent"]) == 1


async def test_follow_unfollow_round_trip(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    investor_id = await _seed_one_trade(repo)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.post(f"/notable-trades/follows/{investor_id}", headers=_AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["investor"]["name"] == "Jane Smith"

    resp = client.delete(f"/notable-trades/follows/{investor_id}", headers=_AUTH)
    assert resp.json()["items"] == []


async def test_follow_requires_pro(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    investor_id = await _seed_one_trade(repo)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.post(f"/notable-trades/follows/{investor_id}", headers=_AUTH)
    assert resp.status_code == 402


async def test_follow_unknown_investor_is_404(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.post(f"/notable-trades/follows/{uuid.uuid4()}", headers=_AUTH)
    assert resp.status_code == 404
