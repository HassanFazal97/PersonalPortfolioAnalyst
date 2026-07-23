"""Risk Lab: the analytics payload, the page render, and the API route."""

from __future__ import annotations

import math
import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.config import DEFAULT_USER_ID, get_settings
from app.main import create_app
from app.tools import market, portfolio, portfolio_risk
from app.tools.tickers import normalize_ticker
from app.webapp import risk_lab_page
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
_AUTH = {"Authorization": "Bearer test-token"}


class _Ctx:
    def __init__(self):
        self.settings = get_settings()
        self.repo = FakeRepo()
        self.user_id = None
        self.timezone = "America/Toronto"


def _walk(seed: float, n: int = 300, vol: float = 0.015) -> list[dict]:
    base = date(2024, 1, 1)
    rows, price, x = [], 100.0, seed
    for i in range(n):
        x = math.sin(x * 12.9898 + 78.233) * 43758.5453
        noise = (x - math.floor(x)) * 2 - 1
        price *= math.exp(vol * noise)
        rows.append({"date": (base + timedelta(days=i)).isoformat(), "adj_close": round(price, 4)})
    return rows


_SERIES = {
    "NVDA": _walk(1.0, vol=0.02),
    "RY.TO": _walk(3.0, vol=0.009),
    "USDCAD=X": _walk(4.0, vol=0.004),
    "^GSPC": _walk(5.0, vol=0.011),
}


async def _fake_pf(payload, ctx):
    return {
        "positions": [
            {"ticker": "NVDA", "currency": "USD", "market_value": 6000.0},
            {"ticker": "RY.TO", "currency": "CAD", "market_value": 4000.0},
        ],
        "totals": {"usdcad_rate": 1.35},
    }


async def test_risk_analytics_payload_shape(monkeypatch):
    market.cache_clear()
    monkeypatch.setattr(portfolio, "get_portfolio", _fake_pf)
    monkeypatch.setattr(
        market, "_fetch_adjusted_closes_raw", lambda t, d: _SERIES[normalize_ticker(t)]
    )

    out = await portfolio_risk.risk_analytics_payload(_Ctx())

    assert out["available"] is True
    s = out["summary"]
    assert s["portfolio_value_cad"] == 12100.0
    assert s["annualized_volatility_pct"] > 0
    assert s["var95_1d_cad"] > 0
    # Correlation matrix is square, unit diagonal, in the holdings' order.
    corr = out["correlation"]
    n = len(corr["tickers"])
    assert n == len(out["holdings"])
    assert all(len(row) == n for row in corr["matrix"])
    for i in range(n):
        assert abs(corr["matrix"][i][i] - 1.0) < 1e-6
    # Monte Carlo fan has 5 ordered bands of equal length.
    bands = out["monte_carlo"]["bands_pct"]
    assert set(bands) == {"p5", "p25", "p50", "p75", "p95"}
    lengths = {len(v) for v in bands.values()}
    assert len(lengths) == 1
    for i in range(len(bands["p5"])):
        assert bands["p5"][i] <= bands["p50"][i] <= bands["p95"][i]


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


def test_risk_analytics_route_requires_auth(monkeypatch):
    client = _client(monkeypatch, FakeRepo())
    assert client.get("/portfolio/risk-analytics").status_code == 401


def test_risk_analytics_route_owner_ok(monkeypatch):
    market.cache_clear()
    monkeypatch.setattr(portfolio, "get_portfolio", _fake_pf)
    monkeypatch.setattr(
        market, "_fetch_adjusted_closes_raw", lambda t, d: _SERIES[normalize_ticker(t)]
    )
    client = _client(monkeypatch, FakeRepo())  # Bearer test-token = owner = Pro
    resp = client.get("/portfolio/risk-analytics", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["summary"]["portfolio_value_cad"] == 12100.0


def test_risk_lab_page_renders():
    html = risk_lab_page("https://x.supabase.co", "anon-key")
    assert "<title>Risk Lab" in html
    assert "/portfolio/risk-analytics" in html
    # The three SVG renderers and the Pro gate are wired in.
    for token in ("renderHeatmap", "renderBars", "renderFan", "risk-gate"):
        assert token in html
