"""``run_valuation_refresh`` job body: reads fundamentals/prices, scores the
universe, writes ``ticker_valuations`` rows."""

from __future__ import annotations

import math
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from tests.fakes import FakeRepo

import app.tools.valuation_refresh as vr
from app.quant import valuation

AS_OF = date.today()


class _Settings:
    picks_history_days = 420
    picks_universe_limit = 0


def _closes(n=300, seed=1.0):
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


def _fund(sector="Technology", fpe=20.0, name="TestCo", mult=1.0):
    return {
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


async def _seed_repo(n=12) -> FakeRepo:
    repo = FakeRepo()
    for i in range(n):
        t = f"T{i:02d}"
        await repo.upsert_ticker_fundamentals(
            ticker=t,
            quote_type="EQUITY",
            data=_fund(fpe=22.0 + i, mult=0.8 + 0.1 * i, name=f"Company {i}"),
        )
        rows = [
            {"date": r["date"], "adj_close": r["adj_close"]} for r in _closes(seed=1.0 + i)
        ]
        await repo.upsert_daily_prices(t, rows)
    # An extra clearly-cheap name so at least one Undervalued verdict lands.
    await repo.upsert_ticker_fundamentals(
        ticker="CHEAP", quote_type="EQUITY",
        data=_fund(fpe=4.0, mult=0.15, name="Cheap Co"),
    )
    await repo.upsert_daily_prices(
        "CHEAP",
        [{"date": r["date"], "adj_close": r["adj_close"]} for r in _closes(seed=99.0)],
    )
    return repo


async def test_refresh_scores_and_persists_universe():
    repo = await _seed_repo()
    tickers = [f"T{i:02d}" for i in range(12)] + ["CHEAP"]
    with patch.object(vr, "get_universe", return_value=tickers):
        result = await vr.run_valuation_refresh(repo, _Settings())

    assert result["tickers"] == len(tickers)
    assert result["scored"] == len(tickers)
    assert sum(result["verdicts"].values()) == len(tickers)

    stored = await repo.get_ticker_valuations()
    assert set(stored) == set(tickers)
    cheap = stored["CHEAP"]
    assert cheap.verdict == valuation.VERDICT_UNDERVALUED
    assert cheap.name == "Cheap Co"
    assert cheap.evidence is not None
    assert cheap.as_of == AS_OF


async def test_refresh_skips_error_rows():
    repo = await _seed_repo(n=3)
    await repo.upsert_ticker_fundamentals(
        ticker="BAD", quote_type=None, data={}, fetch_error="dead ticker"
    )
    tickers = [f"T{i:02d}" for i in range(3)] + ["CHEAP", "BAD"]
    with patch.object(vr, "get_universe", return_value=tickers):
        result = await vr.run_valuation_refresh(repo, _Settings())

    stored = await repo.get_ticker_valuations()
    assert stored["BAD"].verdict == valuation.VERDICT_NOT_SCORED
    assert stored["BAD"].not_scored_reason == "no fundamentals"
    assert result["scored"] == len(tickers)
