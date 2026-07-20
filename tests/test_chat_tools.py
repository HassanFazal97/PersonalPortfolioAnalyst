"""The chat-exposed analytics tools: fundamentals wrapper, portfolio risk,
anomaly scan, and their registry/timeout wiring."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import app.tools.anomalies as anomalies
import app.tools.fundamentals as fundamentals
import app.tools.market as market
import app.tools.portfolio as portfolio
import app.tools.risk as risk
from app.agent.anomaly.scanner import AnomalyFlag
from app.agent.budget import Budget
from app.agent.loop import run_agent
from app.agent.prompts import CHAT_SYSTEM_PROMPT
from app.config import get_settings
from app.tools.registry import CHAT_TOOLS, DISPATCH, TOOL_TIMEOUTS, ToolContext
from tests.fakes import FakeRepo, ScriptedAnthropic, text_turn, tool_use_turn


def _ctx(repo=None):
    return ToolContext(settings=get_settings(), repo=repo or FakeRepo())


def _stored_payload(ticker, *, beta=1.2, days_to_earnings=5):
    upcoming = (
        datetime.now(timezone.utc).date() + timedelta(days=days_to_earnings)
    ).isoformat()
    return {
        "ticker": ticker,
        "quote_type": "EQUITY",
        "profile": {"name": f"{ticker} Corp", "sector": "Tech"},
        "valuation": {"forward_pe": 25.0, "peg": 1.5},
        "growth": {"earnings_growth_pct": 16.7},
        "profitability": {"net_margin_pct": 20.0},
        "financial_health": {"debt_to_equity": 0.5},
        "dividends": {"dividend_rate": 1.0},
        "price_action": {"beta": beta, "beta_source": "yahoo", "high_52w": 100.0},
        "earnings_dates": ["2020-01-01", upcoming],
        "etf": None,
    }


# ---- get_fundamentals wrapper ------------------------------------------------


async def test_fundamentals_tool_trims_and_computes_next_earnings(monkeypatch):
    async def fake_get(tickers, *, repo, settings):
        return {t: _stored_payload(t) for t in tickers}

    monkeypatch.setattr(fundamentals, "get_fundamentals", fake_get)
    out = await fundamentals.get_fundamentals_tool(
        {"tickers": ["NVDA", "SHOP.TO"]}, _ctx()
    )

    nvda = out["fundamentals"]["NVDA"]
    assert nvda["valuation"]["forward_pe"] == 25.0
    assert nvda["price_action"]["beta"] == 1.2
    # Raw history is collapsed to the single upcoming date.
    assert "earnings_dates" not in nvda
    assert nvda["next_earnings_date"] > datetime.now(timezone.utc).date().isoformat()[:4]
    assert "etf" not in nvda  # null etf block is dropped
    assert out["unavailable"] == []


async def test_fundamentals_tool_reports_unavailable_tickers(monkeypatch):
    async def fake_get(tickers, *, repo, settings):
        return {"NVDA": _stored_payload("NVDA")}

    monkeypatch.setattr(fundamentals, "get_fundamentals", fake_get)
    out = await fundamentals.get_fundamentals_tool(
        {"tickers": ["NVDA", "DEADTICKER"]}, _ctx()
    )
    assert out["unavailable"] == ["DEADTICKER"]


# ---- get_portfolio_risk --------------------------------------------------------


def _linear_closes(start, step, n=90):
    return [{"date": f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}", "close": start + step * i}
            for i in range(n)]


async def test_portfolio_risk_composes_weights_beta_and_history(monkeypatch):
    async def fake_pf(payload, ctx):
        return {
            "positions": [
                {"ticker": "NVDA", "currency": "USD", "market_value": 300.0},
                {"ticker": "SHOP.TO", "currency": "CAD", "market_value": 600.0},
            ],
            "totals": {"usdcad_rate": 1.0},
        }

    async def fake_funds(tickers, *, repo, settings):
        return {t: _stored_payload(t, beta=2.0 if t == "NVDA" else 1.0) for t in tickers}

    monkeypatch.setattr(portfolio, "get_portfolio", fake_pf)
    monkeypatch.setattr(fundamentals, "get_fundamentals", fake_funds)
    monkeypatch.setattr(market, "_fetch_history_raw", lambda t, d: _linear_closes(100, 1))

    out = await risk.get_portfolio_risk({}, _ctx())

    by_ticker = {h["ticker"]: h for h in out["holdings"]}
    assert by_ticker["SHOP.TO"]["weight_pct"] == 66.67
    assert by_ticker["NVDA"]["weight_pct"] == 33.33
    assert by_ticker["NVDA"]["beta"] == 2.0
    # Rising linear closes: positive return, zero drawdown.
    assert by_ticker["NVDA"]["period_return_pct"] > 0
    assert by_ticker["NVDA"]["max_drawdown_pct"] == 0.0
    assert by_ticker["NVDA"]["annualized_volatility_pct"] is not None

    p = out["portfolio"]
    assert p["weighted_beta"] == round((2.0 * 33.33 + 1.0 * 66.67) / 100, 2)
    assert p["largest_position_pct"] == 66.67
    assert p["top3_concentration_pct"] == 100.0
    assert p["most_volatile"]["ticker"] in ("NVDA", "SHOP.TO")


async def test_portfolio_risk_caps_to_largest_positions(monkeypatch):
    async def fake_pf(payload, ctx):
        return {
            "positions": [
                {"ticker": f"T{i:02d}.TO", "currency": "CAD", "market_value": 100.0 + i}
                for i in range(12)
            ],
            "totals": {"usdcad_rate": 1.35},
        }

    async def fake_funds(tickers, *, repo, settings):
        return {}

    monkeypatch.setattr(portfolio, "get_portfolio", fake_pf)
    monkeypatch.setattr(fundamentals, "get_fundamentals", fake_funds)
    monkeypatch.setattr(market, "_fetch_history_raw", lambda t, d: _linear_closes(50, 0.5))

    out = await risk.get_portfolio_risk({}, _ctx())
    assert len(out["holdings"]) == risk.MAX_TICKERS
    # The two smallest positions (T00, T01) are the ones skipped.
    assert "T00.TO" in out["note"] and "T01.TO" in out["note"]


async def test_portfolio_risk_handles_empty_portfolio(monkeypatch):
    async def fake_pf(payload, ctx):
        return {"positions": [], "totals": {}, "note": "No positions on record."}

    monkeypatch.setattr(portfolio, "get_portfolio", fake_pf)
    out = await risk.get_portfolio_risk({}, _ctx())
    assert out["holdings"] == []
    assert "No positions" in out["note"]


# ---- scan_anomalies ------------------------------------------------------------


def _flag(ticker):
    return AnomalyFlag(
        ticker=ticker, detector="zscore", direction="down", severity=0.8,
        score=4.2, explanation="4.2 sigma one-day drop", last_close=90.0,
        day_change_pct=-6.0,
    )


async def test_scan_anomalies_defaults_to_holdings(monkeypatch):
    captured = {}

    async def fake_scan(tickers, *, settings):
        captured["tickers"] = tickers
        return {"NVDA": [_flag("NVDA")]}

    monkeypatch.setattr(anomalies, "scan_tickers", fake_scan)
    repo = FakeRepo(positions=[
        SimpleNamespace(ticker="NVDA"), SimpleNamespace(ticker="SHOP.TO"),
    ])
    out = await anomalies.scan_anomalies({}, _ctx(repo))

    assert captured["tickers"] == ["NVDA", "SHOP.TO"]
    assert out["flags"]["NVDA"][0]["detector"] == "zscore"
    assert out["clean"] == ["SHOP.TO"]


async def test_scan_anomalies_caps_ticker_count(monkeypatch):
    async def fake_scan(tickers, *, settings):
        return {}

    monkeypatch.setattr(anomalies, "scan_tickers", fake_scan)
    tickers = [f"T{i:02d}.TO" for i in range(10)]
    out = await anomalies.scan_anomalies({"tickers": tickers}, _ctx())
    assert len(out["clean"]) == anomalies.MAX_TICKERS
    assert "skipped" in out["note"]


# ---- registry + loop wiring ----------------------------------------------------


def test_registry_chat_tools_are_dispatchable_and_unique():
    names = [t["name"] for t in CHAT_TOOLS]
    assert len(names) == 7
    assert len(set(names)) == len(names)
    for name in names:
        assert name in DISPATCH
    for name in TOOL_TIMEOUTS:
        assert name in DISPATCH


async def test_per_tool_timeout_is_honored(monkeypatch):
    async def slow_tool(payload, ctx):
        await asyncio.sleep(0.2)
        return {"ok": True}

    monkeypatch.setitem(DISPATCH, "get_quote", slow_tool)
    monkeypatch.setitem(TOOL_TIMEOUTS, "get_quote", 0.01)

    client = ScriptedAnthropic([
        tool_use_turn("t1", "get_quote", {"tickers": ["NVDA"]}),
        text_turn("done"),
    ])
    repo = FakeRepo()
    budget = Budget(max_iterations=5, max_cost_usd=0.50, model="claude-sonnet-4-6")
    result = await run_agent(
        "q", trigger="chat", system_prompt=CHAT_SYSTEM_PROMPT,
        tools=CHAT_TOOLS, budget=budget, db=repo, client=client,
    )

    assert result.status == "completed"
    call = next(t for t in repo.tool_calls if t["tool_name"] == "get_quote")
    assert call["is_error"] is True
