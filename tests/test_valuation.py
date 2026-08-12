"""Valuation verdict: classification, disclosure, own-history percentile."""

from __future__ import annotations

import math
from datetime import date, timedelta

from app.quant import screener, valuation

AS_OF = date(2026, 8, 8)


def _closes(n=300, seed=1.0):
    """Deterministic pseudo-random walk (same generator as test_screener)."""
    rows, price, x = [], 100.0, seed
    d = AS_OF - timedelta(days=int(n * 1.5))
    while len(rows) < n:
        if d.weekday() < 5:
            x = math.sin(x * 12.9898 + 78.233) * 43758.5453
            noise = (x - math.floor(x)) * 2 - 1
            price *= math.exp(0.0004 + 0.012 * noise)
            rows.append({"date": d.isoformat(), "adj_close": round(price, 4)})
        d += timedelta(days=1)
    rows[-1]["date"] = AS_OF.isoformat()
    return rows


def _fund(sector="Technology", fpe=20.0, name="TestCo", mult=1.0, **over):
    """``mult`` scales every value multiple together (1.0 = the fixture's
    baseline "fairly priced" name) so the sector cross-section has real
    spread on every value metric, not just P/E -- a fixture where the other
    multiples are identical across the sector collapses their MAD to zero
    and silently zeros their contribution to the composite z."""
    data = {
        "quote_type": "EQUITY",
        "profile": {"name": name, "sector": sector, "market_cap": 5e10},
        "valuation": {
            "trailing_pe": fpe * 1.1, "forward_pe": fpe,
            "price_to_sales": round(3.0 * mult, 3),
            "price_to_book": round(4.0 * mult, 3),
            "ev_to_ebitda": round(15.0 * mult, 3),
            "price_to_fcf": round(22.0 * mult, 3),
            "peg": round(1.5 * mult, 3),
        },
        "growth": {"revenue_growth_pct": 8.0, "earnings_growth_pct": 10.0},
        "profitability": {
            "gross_margin_pct": 50.0, "operating_margin_pct": 25.0,
            "net_margin_pct": 18.0, "roe_pct": 20.0,
        },
        "financial_health": {"debt_to_equity": 0.8, "current_ratio": 1.5},
        "price_action": {
            "beta": 1.0, "analyst_target": 130.0, "analyst_count": 10,
            "short_pct_of_float": 1.5, "high_52w": 140.0,
        },
    }
    for dotted, v in over.items():
        section, key = dotted.split(".")
        data[section][key] = v
    return data


def _universe(n=12, sector="Technology"):
    funds, closes = {}, {}
    for i in range(n):
        t = f"T{i:02d}"
        # Spread both P/E and the other value multiples across the sector
        # (0.8x-1.9x of baseline) so no metric's cross-section degenerates.
        funds[t] = _fund(sector=sector, fpe=22.0 + i, mult=0.8 + 0.1 * i)
        closes[t] = _closes(seed=1.0 + i)
    return funds, closes


def _last_price(closes):
    return {t: rows[-1]["adj_close"] for t, rows in closes.items()}


def test_verdict_boundaries():
    assert valuation.verdict_from_z(None) == valuation.VERDICT_NOT_SCORED
    assert valuation.verdict_from_z(1.0) == valuation.VERDICT_UNDERVALUED
    assert valuation.verdict_from_z(2.5) == valuation.VERDICT_UNDERVALUED
    assert valuation.verdict_from_z(-1.0) == valuation.VERDICT_EXPENSIVE
    assert valuation.verdict_from_z(-2.5) == valuation.VERDICT_EXPENSIVE
    assert valuation.verdict_from_z(0.0) == valuation.VERDICT_FAIR
    assert valuation.verdict_from_z(0.99) == valuation.VERDICT_FAIR
    assert valuation.verdict_from_z(-0.99) == valuation.VERDICT_FAIR


def test_value_eligibility():
    assert valuation.value_eligibility(2) is True
    assert valuation.value_eligibility(7) is True
    assert valuation.value_eligibility(1) is False
    assert valuation.value_eligibility(0) is False


def test_cheap_stock_scores_undervalued():
    funds, closes = _universe()
    funds["CHEAP"] = _fund(fpe=4.0, name="Cheap Co", mult=0.15)
    closes["CHEAP"] = _closes(seed=99.0)
    screen = screener.score_universe(funds, closes, as_of=AS_OF)
    rows = {r["ticker"]: r for r in valuation.compute_valuations(screen, funds, _last_price(closes))}
    cheap = rows["CHEAP"]
    assert cheap["verdict"] == valuation.VERDICT_UNDERVALUED
    assert cheap["name"] == "Cheap Co"
    assert cheap["metrics_used"] >= 2
    assert cheap["evidence"]["metrics"]["forward_pe"]["value"] == 4.0
    assert cheap["not_scored_reason"] is None


def test_expensive_stock_scores_expensive():
    funds, closes = _universe()
    funds["RICH"] = _fund(fpe=150.0, name="Rich Co", mult=6.0)
    closes["RICH"] = _closes(seed=98.0)
    screen = screener.score_universe(funds, closes, as_of=AS_OF)
    rows = {r["ticker"]: r for r in valuation.compute_valuations(screen, funds, _last_price(closes))}
    assert rows["RICH"]["verdict"] == valuation.VERDICT_EXPENSIVE


def test_insufficient_value_metrics_not_scored():
    funds, closes = _universe()
    funds["NOVAL"] = _fund(name="No Value Co", **{
        "valuation.trailing_pe": None, "valuation.forward_pe": None,
        "valuation.price_to_sales": None, "valuation.price_to_book": None,
        "valuation.ev_to_ebitda": None, "valuation.price_to_fcf": None,
        "valuation.peg": None,
    })
    closes["NOVAL"] = _closes(seed=60.0)
    screen = screener.score_universe(funds, closes, as_of=AS_OF)
    rows = {r["ticker"]: r for r in valuation.compute_valuations(screen, funds, _last_price(closes))}
    noval = rows["NOVAL"]
    assert noval["verdict"] == valuation.VERDICT_NOT_SCORED
    assert noval["evidence"] is None
    assert noval["not_scored_reason"] == "insufficient factor coverage"
    # Display fields still populate even when unscored (mirrors valucurve's
    # "Not scored" cards, which still show name/price).
    assert noval["name"] == "No Value Co"
    assert noval["last_price"] is not None


def test_non_equity_carries_its_own_reason():
    funds, closes = _universe()
    funds["ETF1"] = {**_fund(), "quote_type": "ETF"}
    closes["ETF1"] = _closes(seed=50.0)
    screen = screener.score_universe(funds, closes, as_of=AS_OF)
    rows = {r["ticker"]: r for r in valuation.compute_valuations(screen, funds, _last_price(closes))}
    assert rows["ETF1"]["verdict"] == valuation.VERDICT_NOT_SCORED
    assert rows["ETF1"]["not_scored_reason"].startswith("not an equity")


def test_value_only_ticker_still_gets_a_verdict():
    """A ticker with priced value metrics but too little else (momentum,
    analyst coverage) fails the picks composite's ``rankable`` gate, but must
    still carry a valuation verdict -- that's the whole point of
    ``value_evidence`` being a superset of ``rows``."""
    funds, closes = _universe()
    funds["THIN"] = _fund(fpe=4.0, name="Thin Co", mult=0.15, **{
        "price_action.analyst_target": None, "price_action.analyst_count": None,
        "growth.revenue_growth_pct": None, "growth.earnings_growth_pct": None,
        "profitability.roe_pct": None, "profitability.gross_margin_pct": None,
        "profitability.operating_margin_pct": None, "profitability.net_margin_pct": None,
        "financial_health.debt_to_equity": None, "financial_health.current_ratio": None,
    })
    closes["THIN"] = _closes(n=205, seed=97.0)  # just above MIN_PRICE_BARS
    screen = screener.score_universe(funds, closes, as_of=AS_OF)
    assert screen.excluded.get("THIN") == "insufficient factor coverage"
    assert all(r["ticker"] != "THIN" for r in screen.rows)
    rows = {r["ticker"]: r for r in valuation.compute_valuations(screen, funds, _last_price(closes))}
    assert rows["THIN"]["verdict"] == valuation.VERDICT_UNDERVALUED
    assert rows["THIN"]["not_scored_reason"] is None


def test_thin_sector_disclosed_as_universe_comparison():
    funds, closes = _universe(n=10, sector="Technology")
    funds["BANK"] = _fund(sector="Financial Services", fpe=8.0, name="Lone Bank")
    closes["BANK"] = _closes(seed=70.0)
    screen = screener.score_universe(funds, closes, as_of=AS_OF)
    rows = {r["ticker"]: r for r in valuation.compute_valuations(screen, funds, _last_price(closes))}
    assert rows["BANK"]["sector_comparison"] == "universe (sector too small)"
    tech_row = next(r for t, r in rows.items() if r["sector"] == "Technology")
    assert tech_row["sector_comparison"] == "sector"


def test_own_history_percentile_requires_minimum_window():
    short_history = [10.0 + i * 0.1 for i in range(10)]
    assert valuation.own_history_percentile(15.0, short_history) is None


def test_own_history_percentile_ranks_within_window():
    history = [10.0 + i * 0.5 for i in range(80)]  # 10.0 .. 49.5
    result = valuation.own_history_percentile(10.0, history)
    assert result is not None
    assert result["window_size"] == 80
    assert result["percentile"] == round(1 / 80 * 100, 1)
