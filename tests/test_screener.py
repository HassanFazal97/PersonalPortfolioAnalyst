"""Factor screener: normalization, ranking, exclusions, movers."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np

from app.quant import screener

AS_OF = date(2026, 7, 24)


def _closes(n=300, drift=0.0004, vol=0.012, last_jump=None, seed=1.0):
    """Deterministic pseudo-random walk (no RNG dependency in tests)."""
    rows, price, x = [], 100.0, seed
    d = AS_OF - timedelta(days=int(n * 1.5))
    while len(rows) < n:
        if d.weekday() < 5:
            x = math.sin(x * 12.9898 + 78.233) * 43758.5453
            noise = (x - math.floor(x)) * 2 - 1
            r = drift + vol * noise
            if last_jump is not None and len(rows) == n - 1:
                r = last_jump
            price *= math.exp(r)
            rows.append({"date": d.isoformat(), "adj_close": round(price, 4)})
        d += timedelta(days=1)
    rows[-1]["date"] = AS_OF.isoformat()
    return rows


def _fund(sector="Technology", fpe=20.0, **over):
    data = {
        "quote_type": "EQUITY",
        "profile": {"name": "TestCo", "sector": sector, "market_cap": 5e10},
        "valuation": {
            "trailing_pe": fpe * 1.1, "forward_pe": fpe, "price_to_sales": 3.0,
            "price_to_book": 4.0, "ev_to_ebitda": 15.0, "price_to_fcf": 22.0,
            "peg": 1.5,
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
        funds[t] = _fund(sector=sector, fpe=22.0 + i)
        closes[t] = _closes(seed=1.0 + i)
    return funds, closes


def test_cheap_stock_ranks_first_on_value():
    funds, closes = _universe()
    funds["CHEAP"] = _fund(fpe=7.0, **{
        "valuation.price_to_sales": 0.9, "valuation.ev_to_ebitda": 5.0,
        "valuation.price_to_fcf": 8.0, "valuation.price_to_book": 1.1,
    })
    closes["CHEAP"] = _closes(seed=99.0)
    res = screener.score_universe(funds, closes, as_of=AS_OF)
    assert res.rows[0]["ticker"] == "CHEAP"
    assert res.rows[0]["rank"] == 1
    ev = res.rows[0]["evidence"]["metrics"]["forward_pe"]
    assert ev["value"] == 7.0
    assert ev["sector_median"] > 7.0  # median of the expensive sector


def test_exclusions_carry_reasons():
    funds, closes = _universe()
    funds["ETF1"] = {**_fund(), "quote_type": "ETF"}
    closes["ETF1"] = _closes(seed=50.0)
    funds["SHORT"] = _fund()
    closes["SHORT"] = _closes(n=100, seed=51.0)
    funds["STALEP"] = _fund()
    stale = _closes(seed=52.0)
    stale = [r for r in stale if r["date"] < (AS_OF - timedelta(days=10)).isoformat()]
    closes["STALEP"] = stale
    funds["NOCAP"] = _fund(**{"profile.market_cap": None})
    closes["NOCAP"] = _closes(seed=53.0)
    closes["NOFUND"] = _closes(seed=54.0)

    res = screener.score_universe(funds, closes, as_of=AS_OF)
    assert res.excluded["ETF1"].startswith("not an equity")
    assert res.excluded["SHORT"] == "insufficient price history"
    assert res.excluded["STALEP"] == "stale prices"
    assert res.excluded["NOCAP"] == "no market cap"
    assert res.excluded["NOFUND"] == "no fundamentals"


def test_stale_fundamentals_gate():
    funds, closes = _universe()
    ages = {t: 1.0 for t in funds}
    ages["T00"] = 72.0
    res = screener.score_universe(
        funds, closes, as_of=AS_OF, fundamentals_age_hours=ages
    )
    assert res.excluded["T00"] == "stale fundamentals"


def test_missing_value_factor_excludes():
    funds, closes = _universe()
    funds["NOVAL"] = _fund(**{
        "valuation.trailing_pe": None, "valuation.forward_pe": None,
        "valuation.price_to_sales": None, "valuation.price_to_book": None,
        "valuation.ev_to_ebitda": None, "valuation.price_to_fcf": None,
        "valuation.peg": None,
    })
    closes["NOVAL"] = _closes(seed=60.0)
    res = screener.score_universe(funds, closes, as_of=AS_OF)
    assert res.excluded["NOVAL"] == "insufficient factor coverage"
    assert all(r["ticker"] != "NOVAL" for r in res.rows)


def test_robust_z_winsorizes_outliers():
    vals = np.array([10.0, 11.0, 12.0, 13.0, 14.0, 400.0])
    z = screener.robust_z(vals)
    assert z[-1] == screener.Z_CLIP
    assert abs(z[2]) < 1.0


def test_small_sector_falls_back_to_universe_stats():
    funds, closes = _universe(n=10, sector="Technology")
    # A lone financial: its sector has 1 name, so it must be normalized
    # against the whole universe rather than itself (which would zero it).
    funds["BANK"] = _fund(sector="Financial Services", fpe=8.0)
    closes["BANK"] = _closes(seed=70.0)
    res = screener.score_universe(funds, closes, as_of=AS_OF)
    bank = next(r for r in res.rows if r["ticker"] == "BANK")
    assert bank["factors"]["value"] > 0  # cheap vs the universe, not zero


def test_daily_return_zscore_math():
    # Flat series with one big last-day jump.
    rows = [
        {"date": (AS_OF - timedelta(days=i)).isoformat(), "adj_close": 100.0}
        for i in range(80, 0, -1)
    ]
    # Give the trailing window tiny alternating moves so sd > 0.
    for i, r in enumerate(rows):
        r["adj_close"] = 100.0 + (0.05 if i % 2 else -0.05)
    rows.append({"date": AS_OF.isoformat(), "adj_close": rows[-1]["adj_close"] * 1.10})
    z = screener.daily_return_zscore(rows)
    assert z is not None and z > screener.MOVER_Z_THRESHOLD


def test_movers_flagged_and_capped():
    funds, closes = _universe()
    funds["JUMP"] = _fund()
    closes["JUMP"] = _closes(last_jump=0.12, seed=80.0)
    funds["DUMP"] = _fund()
    closes["DUMP"] = _closes(last_jump=-0.12, seed=81.0)
    res = screener.score_universe(funds, closes, as_of=AS_OF, max_movers=1)
    assert len(res.movers) == 1
    assert res.movers[0]["ticker"] in ("JUMP", "DUMP")
    assert res.movers[0]["direction"] in ("up", "down")


def test_composite_renormalizes_over_available_factors():
    funds, closes = _universe()
    # Strip analyst coverage from one name: composite must still compute.
    funds["NOAN"] = _fund(fpe=9.0, **{
        "price_action.analyst_target": None, "price_action.analyst_count": None,
    })
    closes["NOAN"] = _closes(seed=90.0)
    res = screener.score_universe(funds, closes, as_of=AS_OF)
    noan = next(r for r in res.rows if r["ticker"] == "NOAN")
    assert noan["composite"] is not None
    assert noan["factors"]["analyst_upside"] is None
