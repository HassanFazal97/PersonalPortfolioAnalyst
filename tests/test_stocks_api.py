"""/portfolio/metrics and /stocks/{ticker} endpoints, offline via FakeRepo."""

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import app.tools.fundamentals as fundamentals
import app.tools.market as market
from app.config import DEFAULT_USER_ID, get_settings
from app.main import create_app
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
_AUTH = {"Authorization": "Bearer test-token"}

NEXT_EARNINGS = (date.today() + timedelta(days=30)).isoformat()
PAST_EARNINGS = (date.today() - timedelta(days=60)).isoformat()


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


PRICES = {"NVDA": 160.0, "VOO": 500.0, "USDCAD=X": 1.35}


def _fake_quote(ticker):
    price = PRICES[ticker]
    return {"last_price": price, "previous_close": price / 1.01, "volume": 100}


def _seed_market(monkeypatch):
    market.cache_clear()
    fundamentals.cache_clear()
    monkeypatch.setattr(market, "_fetch_quote_raw", _fake_quote)


@pytest.fixture()
def repo():
    return FakeRepo()


async def _seed_positions(repo):
    await repo.upsert_position(
        ticker="NVDA", quantity=10, avg_cost=100.0, currency="USD", account="TFSA"
    )
    await repo.upsert_position(
        ticker="NVDA", quantity=5, avg_cost=120.0, currency="USD", account="RRSP"
    )
    await repo.upsert_position(
        ticker="VOO", quantity=2, avg_cost=400.0, currency="USD", account="TFSA"
    )


async def _seed_fundamentals(repo):
    await repo.upsert_ticker_fundamentals(
        ticker="NVDA",
        quote_type="EQUITY",
        data={
            "ticker": "NVDA",
            "quote_type": "EQUITY",
            "profile": {"name": "NVIDIA Corporation", "sector": "Technology"},
            "valuation": {"forward_pe": 32.0, "peg": 0.8},
            "growth": {"earnings_growth_pct": 40.0},
            "profitability": {"roe_pct": 110.0},
            "financial_health": {"debt_to_equity": 0.17},
            "dividends": {"dividend_rate": 0.04, "ex_dividend_date": "2026-06-08"},
            "price_action": {"high_52w": 200.0, "beta": 2.1, "beta_source": "yahoo"},
            "earnings_dates": [PAST_EARNINGS, NEXT_EARNINGS],
            "etf": None,
        },
    )
    await repo.upsert_ticker_fundamentals(
        ticker="VOO",
        quote_type="ETF",
        data={
            "ticker": "VOO",
            "quote_type": "ETF",
            "profile": {"name": "Vanguard S&P 500 ETF"},
            "valuation": {},
            "dividends": {"dividend_rate": 6.75},
            "price_action": {"high_52w": 550.0},
            "earnings_dates": [],
            "etf": {
                "expense_ratio_pct": 0.03,
                "total_assets": 5e11,
                "top_holdings": [{"symbol": "NVDA", "name": "NVIDIA", "weight_pct": 7.5}],
            },
        },
    )


async def test_portfolio_metrics_computes_serve_time_fields(monkeypatch, repo):
    await _seed_positions(repo)
    await _seed_fundamentals(repo)
    _seed_market(monkeypatch)
    resp = _client(monkeypatch, repo).get("/portfolio/metrics", headers=_AUTH)
    assert resp.status_code == 200
    metrics = resp.json()["metrics"]

    nvda = metrics["NVDA"]
    assert nvda["forward_pe"] == 32.0
    assert nvda["beta"] == 2.1
    # Serve-time computed against the live 160 quote.
    assert nvda["pct_from_52w_high"] == -20.0
    assert nvda["dividend_yield_pct"] == round(0.04 / 160.0 * 100, 2)
    assert nvda["next_earnings_date"] == NEXT_EARNINGS

    voo = metrics["VOO"]
    assert voo["quote_type"] == "ETF"
    assert voo["expense_ratio_pct"] == 0.03
    assert voo["next_earnings_date"] is None


async def test_portfolio_metrics_empty_portfolio(monkeypatch, repo):
    _seed_market(monkeypatch)
    resp = _client(monkeypatch, repo).get("/portfolio/metrics", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json() == {"metrics": {}}


async def test_stock_detail_aggregates_position(monkeypatch, repo):
    await _seed_positions(repo)
    await _seed_fundamentals(repo)
    _seed_market(monkeypatch)
    resp = _client(monkeypatch, repo).get("/stocks/NVDA", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()

    assert body["profile"]["ticker"] == "NVDA"
    assert body["profile"]["name"] == "NVIDIA Corporation"
    assert body["quote"]["last_price"] == 160.0

    pos = body["position"]
    # 10 @ 100 (TFSA) + 5 @ 120 (RRSP), both priced at 160.
    assert pos["quantity"] == 15
    assert pos["cost_basis"] == 1600.0
    assert pos["market_value"] == 2400.0
    assert pos["unrealized_pnl"] == 800.0
    assert pos["unrealized_pnl_pct"] == 50.0
    assert len(pos["accounts"]) == 2
    assert pos["annual_dividend_income"] == round(15 * 0.04, 2)
    # NVDA MV = 2400 USD of total (2400 + 1000) USD -> ~70.6% regardless of FX.
    assert abs(pos["weight_pct"] - 70.59) < 0.1

    assert body["earnings"]["next_earnings_date"] == NEXT_EARNINGS
    assert body["price_action"]["pct_from_52w_high"] == -20.0
    assert body["dividends"]["dividend_yield_pct"] == round(0.04 / 160 * 100, 2)
    assert body["fetched_at"] is not None
    assert body["etf"] is None


async def test_stock_detail_etf_branch(monkeypatch, repo):
    await _seed_positions(repo)
    await _seed_fundamentals(repo)
    _seed_market(monkeypatch)
    body = _client(monkeypatch, repo).get("/stocks/VOO", headers=_AUTH).json()
    assert body["profile"]["quote_type"] == "ETF"
    assert body["etf"]["expense_ratio_pct"] == 0.03
    assert body["etf"]["top_holdings"][0]["symbol"] == "NVDA"


async def test_stock_detail_404_when_not_held(monkeypatch, repo):
    await _seed_positions(repo)
    await _seed_fundamentals(repo)
    _seed_market(monkeypatch)
    resp = _client(monkeypatch, repo).get("/stocks/AAPL", headers=_AUTH)
    assert resp.status_code == 404


async def test_stock_detail_rejects_garbage_ticker(monkeypatch, repo):
    _seed_market(monkeypatch)
    client = _client(monkeypatch, repo)
    assert client.get("/stocks/%3Cscript%3E", headers=_AUTH).status_code == 404
    assert client.get("/stocks/AAAAAAAAAAAAAAAAAAAA", headers=_AUTH).status_code == 404


async def test_stock_history_wraps_tool(monkeypatch, repo):
    _seed_market(monkeypatch)
    rows = [
        {"date": "2026-07-01", "open": 1, "high": 1, "low": 1, "close": 100.0, "volume": 1},
        {"date": "2026-07-02", "open": 1, "high": 1, "low": 1, "close": 110.0, "volume": 1},
    ]
    monkeypatch.setattr(market, "_fetch_history_raw", lambda t, d: rows)
    client = _client(monkeypatch, repo)
    body = client.get("/stocks/NVDA/history?days=30", headers=_AUTH).json()
    assert body["bars_returned"] == 2
    assert body["period_return_pct"] == 10.0
    # Validation from the underlying tool surfaces as 400.
    assert client.get("/stocks/NVDA/history?days=4", headers=_AUTH).status_code == 400


async def test_stock_history_days_1_serves_intraday(monkeypatch, repo):
    _seed_market(monkeypatch)
    rows = [
        {"date": "2026-07-15T09:30:00-04:00", "close": 100.0, "volume": 10},
        {"date": "2026-07-15T09:35:00-04:00", "close": 101.0, "volume": 12},
    ]
    monkeypatch.setattr(market, "_fetch_intraday_raw", lambda t: rows)
    body = _client(monkeypatch, repo).get(
        "/stocks/NVDA/history?days=1", headers=_AUTH
    ).json()
    assert body["intraday"] is True
    assert body["interval"] == "5m"
    assert body["bars_returned"] == 2
    assert body["ohlcv"][0]["date"].startswith("2026-07-15T09:30")


async def test_metrics_requires_auth(monkeypatch, repo):
    assert _client(monkeypatch, repo).get("/portfolio/metrics").status_code == 401
    assert _client(monkeypatch, repo).get("/stocks/NVDA").status_code == 401
