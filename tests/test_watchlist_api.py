"""Watchlist API: CRUD, plan caps, junk guard, quotes — offline via FakeRepo."""

import uuid

from fastapi.testclient import TestClient

import app.main as main
import app.tools.fundamentals as fundamentals
import app.tools.market as market
from app.config import DEFAULT_USER_ID, get_settings
from app.main import create_app
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
_AUTH = {"Authorization": "Bearer test-token"}

PRICES = {"NVDA": 160.0, "SHOP.TO": 98.0, "AAPL": 210.0, "VOO": 500.0}


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


def _seed_market(monkeypatch):
    market.cache_clear()
    fundamentals.cache_clear()
    monkeypatch.setattr(
        market, "_fetch_quote_raw",
        lambda t: {"last_price": PRICES[t], "previous_close": PRICES[t] / 1.01,
                   "volume": 100},
    )


async def _seed_fundamentals(repo, *tickers):
    for t in tickers:
        await repo.upsert_ticker_fundamentals(
            ticker=t, quote_type="EQUITY",
            data={"ticker": t, "quote_type": "EQUITY", "profile": {"name": t}},
        )


async def test_watchlist_empty_payload(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    _seed_market(monkeypatch)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    data = client.get("/watchlist", headers=_AUTH).json()
    settings = get_settings()
    assert data == {
        "items": [],
        "limit": settings.free_max_watchlist,
        "used": 0,
        "remaining": settings.free_max_watchlist,
    }


async def test_watch_add_is_idempotent_and_quoted(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    await _seed_fundamentals(repo, "SHOP.TO")
    _seed_market(monkeypatch)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    data = client.post("/watchlist/SHOP.TO", headers=_AUTH).json()
    assert data["used"] == 1
    item = data["items"][0]
    assert item["ticker"] == "SHOP.TO"
    assert item["held"] is False
    assert item["last_price"] == 98.0
    assert item["day_change_pct"] is not None
    assert item["created_at"] is not None

    again = client.post("/watchlist/SHOP.TO", headers=_AUTH).json()
    assert again["used"] == 1


async def test_watch_free_cap_enforced(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    for t in ("NVDA", "SHOP.TO", "VOO"):
        await repo.add_watchlist_ticker(uid, t)
    await _seed_fundamentals(repo, "AAPL")
    _seed_market(monkeypatch)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.post("/watchlist/AAPL", headers=_AUTH)
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "Free plan allows at most 3" in detail
    assert "Upgrade to Pro" in detail
    # Re-adding an already-watched ticker still succeeds at the cap.
    assert client.post("/watchlist/NVDA", headers=_AUTH).status_code == 200


async def test_watch_pro_cap_enforced(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    settings_cap = get_settings().pro_max_watchlist
    for i in range(settings_cap):
        await repo.add_watchlist_ticker(uid, f"T{i}")
    await _seed_fundamentals(repo, "AAPL")
    _seed_market(monkeypatch)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.post("/watchlist/AAPL", headers=_AUTH)
    assert resp.status_code == 400
    assert f"Pro plan allows at most {settings_cap}" in resp.json()["detail"]
    assert "Upgrade" not in resp.json()["detail"]


async def test_watch_owner_exempt_from_cap(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    for i in range(get_settings().pro_max_watchlist):
        await repo.add_watchlist_ticker(_OWNER, f"T{i}")
    await _seed_fundamentals(repo, "AAPL")
    _seed_market(monkeypatch)
    client = _client(monkeypatch, repo)

    data = client.post("/watchlist/AAPL", headers=_AUTH).json()
    assert data["limit"] is None
    assert data["remaining"] is None
    assert data["used"] == get_settings().pro_max_watchlist + 1


async def test_watch_unknown_ticker_404(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    market.cache_clear()
    fundamentals.cache_clear()

    def no_quote(_t):
        raise RuntimeError("no such ticker")

    monkeypatch.setattr(market, "_fetch_quote_raw", no_quote)
    monkeypatch.setattr(fundamentals, "_fetch_fundamentals_raw", no_quote)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    assert client.post("/watchlist/ZZZQ", headers=_AUTH).status_code == 404
    assert await repo.get_watchlist_tickers(uid) == []


async def test_watch_all_none_skeleton_404(monkeypatch):
    """A garbage ticker whose Yahoo .info normalized to an all-None skeleton
    row must not be watchable (it would join the nightly job loops)."""
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    await repo.upsert_ticker_fundamentals(
        ticker="ZZZQ", quote_type=None,
        data={"ticker": "ZZZQ", "quote_type": None,
              "profile": {"name": None}, "valuation": {}},
    )
    market.cache_clear()
    fundamentals.cache_clear()

    def no_quote(_t):
        raise RuntimeError("no such ticker")

    monkeypatch.setattr(market, "_fetch_quote_raw", no_quote)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    assert client.post("/watchlist/ZZZQ", headers=_AUTH).status_code == 404
    assert await repo.get_watchlist_tickers(uid) == []


async def test_unwatch_removes(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    await repo.add_watchlist_ticker(uid, "NVDA")
    _seed_market(monkeypatch)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    data = client.delete("/watchlist/NVDA", headers=_AUTH).json()
    assert data["items"] == []
    assert data["used"] == 0


async def test_watchlist_flags_held_tickers(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    await repo.upsert_position(
        ticker="NVDA", quantity=1, avg_cost=100.0, currency="USD",
        account="TFSA", user_id=uid,
    )
    await repo.add_watchlist_ticker(uid, "NVDA")
    await repo.add_watchlist_ticker(uid, "SHOP.TO")
    _seed_market(monkeypatch)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    items = {i["ticker"]: i for i in client.get("/watchlist", headers=_AUTH).json()["items"]}
    assert items["NVDA"]["held"] is True
    assert items["SHOP.TO"]["held"] is False


async def test_watchlist_requires_auth(monkeypatch):
    repo = FakeRepo()
    client = _client(monkeypatch, repo)
    assert client.get("/watchlist").status_code == 401
    assert client.post("/watchlist/NVDA").status_code == 401
