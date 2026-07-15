from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import app.tools.fundamentals as fundamentals
from app.tools.fundamentals import (
    _normalize_fundamentals,
    annual_dividend_income,
    beta_from_closes,
    dividend_yield_pct,
    get_fundamentals,
    next_earnings_date,
    pct_from_52w_high,
    peg_ratio,
    price_to_fcf,
    run_fundamentals_refresh,
)


def test_peg_ratio():
    assert peg_ratio(30.0, 25.0) == 1.2
    assert peg_ratio(30.0, 0.0) is None  # zero growth
    assert peg_ratio(30.0, -10.0) is None  # negative growth
    assert peg_ratio(None, 25.0) is None
    assert peg_ratio(30.0, None) is None


def test_dividend_yield_pct():
    assert dividend_yield_pct(4.0, 100.0) == 4.0
    assert dividend_yield_pct(None, 100.0) is None
    assert dividend_yield_pct(4.0, None) is None
    assert dividend_yield_pct(4.0, 0.0) is None


def test_price_to_fcf():
    assert price_to_fcf(1000.0, 100.0) == 10.0
    assert price_to_fcf(1000.0, -5.0) is None  # negative FCF
    assert price_to_fcf(None, 100.0) is None


def test_pct_from_52w_high():
    assert pct_from_52w_high(80.0, 100.0) == -20.0
    assert pct_from_52w_high(100.0, 100.0) == 0.0
    assert pct_from_52w_high(None, 100.0) is None
    assert pct_from_52w_high(80.0, 0.0) is None


def test_annual_dividend_income():
    assert annual_dividend_income(10.0, 4.0) == 40.0
    assert annual_dividend_income(10.0, None) is None
    assert annual_dividend_income(0.0, 4.0) is None


def test_next_earnings_date():
    today = date(2026, 7, 15)
    assert next_earnings_date(["2026-05-01", "2026-08-27"], today) == "2026-08-27"
    assert next_earnings_date(["2026-07-15"], today) == "2026-07-15"  # today counts
    assert next_earnings_date(["2026-05-01"], today) is None  # all past
    assert next_earnings_date([], today) is None
    assert next_earnings_date(None, today) is None


def _bars(start_day: int, closes: list[float], skip_days: set[int] | None = None):
    rows = []
    day = start_day
    for c in closes:
        while skip_days and day in skip_days:
            day += 1
        rows.append({"date": f"2026-01-{day:02d}", "close": c})
        day += 1
    return rows


def test_beta_from_closes_matches_hand_computation():
    # Asset daily return is exactly 2x the benchmark's (varying) return -> beta 2.
    n = 70
    bench_returns = [0.01 if i % 2 == 0 else -0.005 for i in range(n - 1)]
    bench, asset = [100.0], [50.0]
    for r in bench_returns:
        bench.append(bench[-1] * (1 + r))
        asset.append(asset[-1] * (1 + 2 * r))
    beta = beta_from_closes(_bars(1, asset), _bars(1, bench))
    assert beta is not None
    assert abs(beta - 2.0) < 0.05


def test_beta_from_closes_requires_overlap():
    short = _bars(1, [100.0, 101.0, 102.0])
    assert beta_from_closes(short, short) is None
    # Disjoint calendars (no common dates) -> None.
    a = [{"date": f"2026-03-{d:02d}", "close": 100.0 + d} for d in range(1, 28)]
    b = [{"date": f"2026-04-{d:02d}", "close": 100.0 + d} for d in range(1, 28)]
    assert beta_from_closes(a, b) is None


def test_beta_zero_variance_benchmark():
    n = 70
    flat = [100.0] * n
    asset = [100.0 * (1.01**i) for i in range(n)]
    assert beta_from_closes(_bars(1, asset), _bars(1, flat)) is None


STOCK_INFO = {
    "quoteType": "EQUITY",
    "longName": "NVIDIA Corporation",
    "sector": "Technology",
    "industry": "Semiconductors",
    "currency": "USD",
    "marketCap": 4_000_000_000_000,
    "trailingPE": 50.0,
    "forwardPE": 30.0,
    "priceToSalesTrailing12Months": 25.0,
    "priceToBook": 40.0,
    "enterpriseToEbitda": 45.0,
    "freeCashflow": 80_000_000_000,
    "revenueGrowth": 0.60,
    "earningsGrowth": 0.75,
    "grossMargins": 0.75,
    "operatingMargins": 0.60,
    "profitMargins": 0.55,
    "returnOnEquity": 1.10,
    "debtToEquity": 17.2,
    "currentRatio": 4.1,
    "dividendRate": 0.04,
    "payoutRatio": 0.01,
    "exDividendDate": 1780000000,
    "fiftyTwoWeekHigh": 200.0,
    "fiftyTwoWeekLow": 90.0,
    "beta": 2.1,
    "fiftyDayAverage": 170.0,
    "twoHundredDayAverage": 150.0,
    "targetMeanPrice": 210.0,
    "recommendationKey": "buy",
    "recommendationMean": 1.7,
    "numberOfAnalystOpinions": 55,
    "shortPercentOfFloat": 0.011,
}


def test_normalize_stock():
    raw = {
        "info": STOCK_INFO,
        "calendar": {"Earnings Date": [date(2026, 8, 27), date(2026, 9, 1)]},
    }
    data = _normalize_fundamentals("NVDA", raw)
    assert data["quote_type"] == "EQUITY"
    assert data["profile"]["name"] == "NVIDIA Corporation"
    assert data["valuation"]["forward_pe"] == 30.0
    # PEG computed from parts: 30 / 75 = 0.4
    assert data["valuation"]["peg"] == 0.4
    # P/FCF computed: 4T / 80B = 50
    assert data["valuation"]["price_to_fcf"] == 50.0
    assert data["growth"]["revenue_growth_pct"] == 60.0
    assert data["profitability"]["roe_pct"] == 110.0
    # debtToEquity percent -> ratio
    assert data["financial_health"]["debt_to_equity"] == 0.17
    assert data["dividends"]["payout_ratio_pct"] == 1.0
    assert data["dividends"]["ex_dividend_date"] == "2026-05-28"
    assert data["price_action"]["beta"] == 2.1
    assert data["price_action"]["beta_source"] == "yahoo"
    assert data["price_action"]["short_pct_of_float"] == 1.1
    assert data["earnings_dates"] == ["2026-08-27", "2026-09-01"]
    assert data["etf"] is None


def test_normalize_etf():
    raw = {
        "info": {
            "quoteType": "ETF",
            "longName": "Vanguard S&P 500 ETF",
            "currency": "USD",
            "totalAssets": 500_000_000_000,
            "netExpenseRatio": 0.03,
            "trailingAnnualDividendRate": 6.5,
            "fiftyTwoWeekHigh": 600.0,
            "category": "Large Blend",
            "fundFamily": "Vanguard",
        },
        "calendar": {},
        "top_holdings": [
            {"symbol": "NVDA", "name": "NVIDIA Corp", "weight": 0.075},
            {"symbol": "MSFT", "name": "Microsoft Corp", "weight": 0.065},
        ],
        "fund_ops_expense_ratio": 0.0003,
    }
    data = _normalize_fundamentals("VOO", raw)
    assert data["quote_type"] == "ETF"
    # netExpenseRatio is already percent — used as-is.
    assert data["etf"]["expense_ratio_pct"] == 0.03
    assert data["etf"]["total_assets"] == 500_000_000_000
    assert data["etf"]["top_holdings"][0] == {
        "symbol": "NVDA",
        "name": "NVIDIA Corp",
        "weight_pct": 7.5,
    }
    # ETFs: dividend rate falls back to trailingAnnualDividendRate.
    assert data["dividends"]["dividend_rate"] == 6.5
    assert data["price_action"]["beta"] is None
    assert data["price_action"]["beta_source"] is None


def test_normalize_etf_expense_ratio_fallback():
    raw = {
        "info": {"quoteType": "ETF"},
        "calendar": {},
        "top_holdings": None,
        "fund_ops_expense_ratio": 0.0009,
    }
    data = _normalize_fundamentals("XIU.TO", raw)
    # funds_data fallback is a fraction -> percent.
    assert data["etf"]["expense_ratio_pct"] == 0.09
    assert data["etf"]["top_holdings"] == []


def test_normalize_missing_everything():
    # Crypto/FX-style payload: nothing useful. Every field must be None-safe.
    data = _normalize_fundamentals("BTC-USD", {"info": {"quoteType": "CRYPTOCURRENCY"}})
    assert data["quote_type"] == "CRYPTOCURRENCY"
    assert data["valuation"]["trailing_pe"] is None
    assert data["valuation"]["peg"] is None
    assert data["dividends"]["dividend_rate"] is None
    assert data["earnings_dates"] == []
    assert data["etf"] is None


def test_normalize_rejects_non_numeric_garbage():
    data = _normalize_fundamentals(
        "X", {"info": {"quoteType": "EQUITY", "trailingPE": "Infinity", "beta": float("nan")}}
    )
    assert data["valuation"]["trailing_pe"] is None
    assert data["price_action"]["beta"] is None


# --------------------------------------------------------------------------
# Cache orchestration
# --------------------------------------------------------------------------

SETTINGS = SimpleNamespace(
    fundamentals_ttl_hours=24,
    fundamentals_error_ttl_hours=1,
    fundamentals_beta_benchmark="^GSPC",
)


def _fake_raw(ticker, *, beta=2.0):
    info = {"quoteType": "EQUITY", "longName": f"{ticker} Inc", "forwardPE": 20.0}
    if beta is not None:
        info["beta"] = beta
    return {"info": info, "calendar": {}}


def _repo():
    from tests.fakes import FakeRepo

    return FakeRepo()


async def test_get_fundamentals_fetches_and_persists(monkeypatch):
    fundamentals.cache_clear()
    repo = _repo()
    calls = {"n": 0}

    def fake_fetch(ticker):
        calls["n"] += 1
        return _fake_raw(ticker)

    monkeypatch.setattr(fundamentals, "_fetch_fundamentals_raw", fake_fetch)
    out = await get_fundamentals(["nvda"], repo=repo, settings=SETTINGS)
    assert out["NVDA"]["profile"]["name"] == "NVDA Inc"
    assert "NVDA" in repo.ticker_fundamentals
    # Second call within the in-process TTL: no new fetch, no DB read needed.
    await get_fundamentals(["NVDA"], repo=repo, settings=SETTINGS)
    assert calls["n"] == 1


async def test_get_fundamentals_serves_fresh_db_row_without_fetch(monkeypatch):
    fundamentals.cache_clear()
    repo = _repo()
    await repo.upsert_ticker_fundamentals(
        ticker="NVDA", quote_type="EQUITY", data={"ticker": "NVDA", "x": 1}
    )

    def boom(ticker):
        raise AssertionError("must not fetch")

    monkeypatch.setattr(fundamentals, "_fetch_fundamentals_raw", boom)
    out = await get_fundamentals(["NVDA"], repo=repo, settings=SETTINGS)
    assert out["NVDA"]["x"] == 1


async def test_get_fundamentals_stale_serves_immediately_and_revalidates(monkeypatch):
    fundamentals.cache_clear()
    repo = _repo()
    await repo.upsert_ticker_fundamentals(
        ticker="NVDA", quote_type="EQUITY", data={"ticker": "NVDA", "stale": True}
    )
    # Age the row past the TTL.
    repo.ticker_fundamentals["NVDA"].fetched_at = datetime.now(timezone.utc) - timedelta(
        hours=48
    )
    monkeypatch.setattr(fundamentals, "_fetch_fundamentals_raw", _fake_raw)

    out = await get_fundamentals(["NVDA"], repo=repo, settings=SETTINGS)
    # Stale data served without blocking on the network...
    assert out["NVDA"] == {"ticker": "NVDA", "stale": True}
    # ...while a background refresh replaces it.
    assert "NVDA" in fundamentals._refresh_tasks
    await fundamentals._refresh_tasks["NVDA"]
    assert repo.ticker_fundamentals["NVDA"].data["profile"]["name"] == "NVDA Inc"


async def test_get_fundamentals_error_row_respects_short_ttl(monkeypatch):
    fundamentals.cache_clear()
    repo = _repo()
    calls = {"n": 0}

    def always_fails(ticker):
        calls["n"] += 1
        raise RuntimeError("no fundamentals")

    monkeypatch.setattr(fundamentals, "_fetch_fundamentals_raw", always_fails)
    out = await get_fundamentals(["BTC-USD"], repo=repo, settings=SETTINGS)
    assert out == {}
    assert repo.ticker_fundamentals["BTC-USD"].fetch_error is not None
    # Fresh error row: no re-fetch.
    await get_fundamentals(["BTC-USD"], repo=repo, settings=SETTINGS)
    assert calls["n"] == 1
    # Past the error TTL: retried.
    repo.ticker_fundamentals["BTC-USD"].fetched_at = datetime.now(
        timezone.utc
    ) - timedelta(hours=2)
    await get_fundamentals(["BTC-USD"], repo=repo, settings=SETTINGS)
    assert calls["n"] == 2


async def test_computed_beta_fallback(monkeypatch):
    fundamentals.cache_clear()
    repo = _repo()
    monkeypatch.setattr(
        fundamentals, "_fetch_fundamentals_raw", lambda t: _fake_raw(t, beta=None)
    )

    n = 70
    bench_returns = [0.01 if i % 2 == 0 else -0.005 for i in range(n - 1)]
    bench, asset = [100.0], [50.0]
    for r in bench_returns:
        bench.append(bench[-1] * (1 + r))
        asset.append(asset[-1] * (1 + 2 * r))

    def fake_history(ticker, days):
        closes = bench if ticker == "^GSPC" else asset
        return _bars(1, closes)

    monkeypatch.setattr(fundamentals.market, "_fetch_history_raw", fake_history)
    out = await get_fundamentals(["SHOP.TO"], repo=repo, settings=SETTINGS)
    pa = out["SHOP.TO"]["price_action"]
    assert pa["beta_source"] == "computed"
    assert abs(pa["beta"] - 2.0) < 0.05


async def test_run_fundamentals_refresh_covers_all_tickers(monkeypatch):
    fundamentals.cache_clear()
    repo = _repo()
    await repo.upsert_position(
        ticker="NVDA", quantity=1, avg_cost=100, currency="USD", account="TFSA"
    )
    await repo.upsert_position(
        ticker="SHOP.TO", quantity=2, avg_cost=50, currency="CAD", account="RRSP"
    )
    monkeypatch.setattr(fundamentals, "REFRESH_SPACING_SECONDS", 0)
    monkeypatch.setattr(fundamentals, "_fetch_fundamentals_raw", _fake_raw)
    summary = await run_fundamentals_refresh(repo, SETTINGS)
    assert summary == {"tickers": 2, "refreshed": 2, "failed": 0}
    assert set(repo.ticker_fundamentals) == {"NVDA", "SHOP.TO"}


async def test_get_fundamentals_bounds_concurrency(monkeypatch):
    fundamentals.cache_clear()
    repo = _repo()
    in_flight = {"now": 0, "max": 0}

    def slow_fetch(ticker):
        # Runs in a thread; count concurrent entries.
        in_flight["now"] += 1
        in_flight["max"] = max(in_flight["max"], in_flight["now"])
        import time as _time

        _time.sleep(0.05)
        in_flight["now"] -= 1
        return _fake_raw(ticker)

    monkeypatch.setattr(fundamentals, "_fetch_fundamentals_raw", slow_fetch)
    tickers = [f"T{i}" for i in range(10)]
    out = await get_fundamentals(tickers, repo=repo, settings=SETTINGS)
    assert len(out) == 10
    assert in_flight["max"] <= fundamentals.FETCH_CONCURRENCY
