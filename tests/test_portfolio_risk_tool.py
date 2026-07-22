"""Integration test for the analyze_portfolio_risk tool (fetch seam mocked)."""

from __future__ import annotations

import math
from datetime import date, timedelta

from app.config import get_settings
from app.tools import market, portfolio, portfolio_risk
from app.tools.registry import DISPATCH, TOOL_TIMEOUTS
from app.tools.tickers import normalize_ticker
from tests.fakes import FakeRepo


class _Ctx:
    def __init__(self):
        self.settings = get_settings()
        self.repo = FakeRepo()
        self.user_id = None
        self.timezone = "America/Toronto"


def _walk(seed: float, n: int = 300, vol: float = 0.01) -> list[dict]:
    """Deterministic pseudo-random geometric walk of adjusted closes."""
    base = date(2024, 1, 1)
    rows = []
    price = 100.0
    x = seed
    for i in range(n):
        # cheap deterministic "noise" in [-1, 1] without Math.random
        x = math.sin(x * 12.9898 + 78.233) * 43758.5453
        noise = (x - math.floor(x)) * 2 - 1
        price *= math.exp(vol * noise)
        rows.append({"date": (base + timedelta(days=i)).isoformat(), "adj_close": round(price, 4)})
    return rows


async def test_analyze_portfolio_risk_produces_coherent_decomposition(monkeypatch):
    async def fake_pf(payload, ctx):
        return {
            "positions": [
                {"ticker": "NVDA", "currency": "USD", "market_value": 5000.0},
                {"ticker": "MSFT", "currency": "USD", "market_value": 3000.0},
                {"ticker": "RY.TO", "currency": "CAD", "market_value": 2000.0},
            ],
            "totals": {"usdcad_rate": 1.35},
        }

    series = {
        "NVDA": _walk(1.0, vol=0.02),
        "MSFT": _walk(2.0, vol=0.015),
        "RY.TO": _walk(3.0, vol=0.008),
        "USDCAD=X": _walk(4.0, vol=0.004),
    }

    market.cache_clear()
    monkeypatch.setattr(portfolio, "get_portfolio", fake_pf)
    monkeypatch.setattr(
        market, "_fetch_adjusted_closes_raw", lambda t, d: series[normalize_ticker(t)]
    )

    out = await portfolio_risk.analyze_portfolio_risk({}, _Ctx())

    p = out["portfolio"]
    assert p["holdings_analyzed"] == 3
    assert p["annualized_volatility_pct"] > 0
    # Diversification: true portfolio vol should not exceed the naive weighted
    # average, and the ratio is >= 1.
    assert p["annualized_volatility_pct"] <= p["weighted_avg_volatility_pct"] + 1e-6
    assert p["diversification_ratio"] >= 1.0
    assert 0.0 <= p["covariance_shrinkage"] <= 1.0
    assert 1 <= p["effective_number_of_bets"] <= 3 + 1e-9

    # Risk contributions form a proper decomposition summing to 100%.
    total_risk = sum(h["risk_contribution_pct"] for h in out["holdings"])
    assert abs(total_risk - 100.0) < 0.5  # rounding of per-holding values

    # Every holding carries the story metric.
    for h in out["holdings"]:
        assert "risk_vs_weight_gap_pct" in h


async def test_estimate_downside_risk_produces_var_cvar_and_scenarios(monkeypatch):
    async def fake_pf(payload, ctx):
        return {
            "positions": [
                {"ticker": "NVDA", "currency": "USD", "market_value": 6000.0},
                {"ticker": "RY.TO", "currency": "CAD", "market_value": 4000.0},
            ],
            "totals": {"usdcad_rate": 1.35},
        }

    series = {
        "NVDA": _walk(1.0, vol=0.02),
        "RY.TO": _walk(3.0, vol=0.009),
        "USDCAD=X": _walk(4.0, vol=0.004),
        "^GSPC": _walk(5.0, vol=0.011),
    }

    market.cache_clear()
    monkeypatch.setattr(portfolio, "get_portfolio", fake_pf)
    monkeypatch.setattr(
        market, "_fetch_adjusted_closes_raw", lambda t, d: series[normalize_ticker(t)]
    )

    out = await portfolio_risk.estimate_downside_risk({}, _Ctx())

    # NVDA USD 6000 × 1.35 + RY.TO CAD 4000 = 12100 CAD.
    assert out["portfolio_value_cad"] == 12100.0
    var = {b["confidence_pct"]: b for b in out["value_at_risk"]}
    # 99% VaR is at least the 95% VaR; both positive losses.
    assert var[99.0]["daily_var_pct"] >= var[95.0]["daily_var_pct"] > 0
    # CVaR >= VaR at each level.
    assert var[95.0]["daily_cvar_pct"] >= var[95.0]["daily_var_pct"] - 1e-9
    # CAD figures scale off portfolio value.
    assert var[95.0]["daily_var_cad"] > 0
    # Monthly VaR (√21-scaled) exceeds the 1-day VaR.
    assert var[95.0]["monthly_var_pct"] > var[95.0]["daily_var_pct"]
    # Worst realized block and scenarios present.
    assert out["worst_historical"]["max_drawdown_pct"] >= 0
    assert out["portfolio_beta"] is not None
    assert len(out["scenarios"]) == 3
    crash = out["scenarios"][-1]
    assert crash["estimated_portfolio_return_pct"] < 0  # a down shock -> a loss


async def test_analyze_portfolio_risk_needs_two_holdings(monkeypatch):
    async def fake_pf(payload, ctx):
        return {
            "positions": [{"ticker": "NVDA", "currency": "USD", "market_value": 5000.0}],
            "totals": {"usdcad_rate": 1.35},
        }

    monkeypatch.setattr(portfolio, "get_portfolio", fake_pf)
    out = await portfolio_risk.analyze_portfolio_risk({}, _Ctx())
    assert "note" in out


async def test_analyze_portfolio_risk_empty_portfolio(monkeypatch):
    async def fake_pf(payload, ctx):
        return {"positions": [], "totals": {}}

    monkeypatch.setattr(portfolio, "get_portfolio", fake_pf)
    out = await portfolio_risk.analyze_portfolio_risk({}, _Ctx())
    assert out["note"] == "No positions on record."


def test_tools_are_registered_and_pro_gated():
    from app.tools.registry import (
        ANALYZE_PORTFOLIO_RISK_SCHEMA,
        CHAT_TOOLS,
        ESTIMATE_DOWNSIDE_RISK_SCHEMA,
        PRO_CHAT_TOOLS,
    )

    for name in ("analyze_portfolio_risk", "estimate_downside_risk"):
        assert name in DISPATCH
        assert name in TOOL_TIMEOUTS
    assert ANALYZE_PORTFOLIO_RISK_SCHEMA in PRO_CHAT_TOOLS
    assert ESTIMATE_DOWNSIDE_RISK_SCHEMA in PRO_CHAT_TOOLS
    # They must NOT be in the Free roster.
    names = {t.get("name") for t in CHAT_TOOLS}
    assert "analyze_portfolio_risk" not in names
    assert "estimate_downside_risk" not in names
