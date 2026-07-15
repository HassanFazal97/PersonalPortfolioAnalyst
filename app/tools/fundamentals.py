"""Per-ticker fundamentals: yfinance ``.info`` snapshot + derived metrics.

Follows the market.py conventions: yfinance isolated behind a sync fetch seam
(``_fetch_fundamentals_raw``) that tests patch, normalization and every derived
metric computed in Python. Several metrics are deliberately computed from
parts rather than trusted from the API — yfinance's ``pegRatio`` was removed
and ``dividendYield`` changed semantics across versions.

Fundamentals change slowly, so unlike quotes they persist in the global
``ticker_fundamentals`` table (one row per ticker, shared across users) and
are refreshed nightly plus lazily on read; see ``get_fundamentals``.
"""

from __future__ import annotations

import asyncio
import math
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.tools import market
from app.tools.tickers import normalize_tickers

# Minimum overlapping daily returns for a computed beta to be meaningful.
BETA_MIN_OVERLAP = 60

# In-process layer in front of the DB so repeat page loads cost zero queries.
MEM_TTL_SECONDS = 300.0
# Benchmark closes reused across computed-beta fallbacks (nightly job would
# otherwise re-download ^GSPC once per beta-less ticker).
BENCH_TTL_SECONDS = 3600.0
# Concurrent lazy fetches per request — .info is the Yahoo-429-prone call.
FETCH_CONCURRENCY = 4
# Spacing between tickers in the nightly refresh, for the same reason.
REFRESH_SPACING_SECONDS = 0.75

# ticker -> (monotonic_timestamp, normalized_data_dict)
_mem_cache: dict[str, tuple[float, dict[str, Any]]] = {}
# benchmark ticker -> (monotonic_timestamp, history rows)
_bench_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
# tickers with an in-flight background (stale-while-revalidate) refresh
_refresh_tasks: dict[str, asyncio.Task] = {}


def _clock() -> float:
    return time.monotonic()


def cache_clear() -> None:
    """Test/utility helper to reset the in-process caches."""
    _mem_cache.clear()
    _bench_cache.clear()
    _refresh_tasks.clear()


def _num(v: Any) -> float | None:
    """Coerce a yfinance .info value to a finite float, else None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and math.isfinite(v):
        return float(v)
    return None


# --------------------------------------------------------------------------
# Pure metric helpers (unit-tested directly)
# --------------------------------------------------------------------------


def peg_ratio(forward_pe: float | None, earnings_growth_pct: float | None) -> float | None:
    """PEG from parts. ``earnings_growth_pct`` is a percentage (25.0 = 25%)."""
    if forward_pe is None or earnings_growth_pct is None or earnings_growth_pct <= 0:
        return None
    return round(forward_pe / earnings_growth_pct, 2)


def dividend_yield_pct(dividend_rate: float | None, last_price: float | None) -> float | None:
    """Yield from $/share/yr and live price — unambiguous across yf versions."""
    if dividend_rate is None or not last_price or last_price <= 0:
        return None
    return round(dividend_rate / last_price * 100, 2)


def price_to_fcf(market_cap: float | None, free_cashflow: float | None) -> float | None:
    if market_cap is None or free_cashflow is None or free_cashflow <= 0:
        return None
    return round(market_cap / free_cashflow, 2)


def pct_from_52w_high(last_price: float | None, high_52w: float | None) -> float | None:
    if last_price is None or not high_52w or high_52w <= 0:
        return None
    return round((last_price / high_52w - 1) * 100, 2)


def annual_dividend_income(quantity: float, dividend_rate: float | None) -> float | None:
    if dividend_rate is None or quantity <= 0:
        return None
    return round(quantity * dividend_rate, 2)


def next_earnings_date(earnings_dates: list[str] | None, today: date) -> str | None:
    """Earliest stored earnings date on/after ``today`` (dates are ISO strings)."""
    if not earnings_dates:
        return None
    upcoming = sorted(d for d in earnings_dates if d >= today.isoformat())
    return upcoming[0] if upcoming else None


def beta_from_closes(
    asset_rows: list[dict[str, Any]], bench_rows: list[dict[str, Any]]
) -> float | None:
    """Beta = cov(asset, benchmark) / var(benchmark) over date-aligned daily returns.

    Rows are ``{"date": iso, "close": float}`` bars (the ``_fetch_history_raw``
    shape). Aligning by date matters: TSX and NYSE holidays differ, so a
    positional zip would smear returns across mismatched days.
    """
    a = {r["date"]: r["close"] for r in asset_rows}
    b = {r["date"]: r["close"] for r in bench_rows}
    common = sorted(set(a) & set(b))
    if len(common) < BETA_MIN_OVERLAP + 1:
        return None
    ra: list[float] = []
    rb: list[float] = []
    for prev, cur in zip(common, common[1:]):
        if a[prev] and b[prev]:
            ra.append(a[cur] / a[prev] - 1)
            rb.append(b[cur] / b[prev] - 1)
    if len(ra) < BETA_MIN_OVERLAP:
        return None
    mean_a = sum(ra) / len(ra)
    mean_b = sum(rb) / len(rb)
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(ra, rb)) / (len(ra) - 1)
    var = sum((y - mean_b) ** 2 for y in rb) / (len(rb) - 1)
    if var == 0:
        return None
    return round(cov / var, 2)


# --------------------------------------------------------------------------
# Network seam (patched in tests)
# --------------------------------------------------------------------------


def _fetch_fundamentals_raw(ticker: str) -> dict[str, Any]:
    """One slow yfinance pass per ticker: ``.info`` + calendar (+ ETF extras).

    ``.info`` failures propagate — the caller records an error row so a dead
    ticker isn't re-fetched on every request. The auxiliary surfaces (calendar,
    funds_data) are individually swallowed: they're flaky and partial data
    beats none.
    """
    import yfinance as yf

    t = yf.Ticker(ticker)
    raw: dict[str, Any] = {"info": dict(t.info or {})}

    try:
        raw["calendar"] = dict(t.calendar or {})
    except Exception:
        raw["calendar"] = {}

    if raw["info"].get("quoteType") == "ETF":
        try:
            df = t.funds_data.top_holdings
            raw["top_holdings"] = [
                {
                    "symbol": str(idx),
                    "name": str(row.get("Name") or ""),
                    "weight": float(row["Holding Percent"]),
                }
                for idx, row in df.head(10).iterrows()
            ]
        except Exception:
            raw["top_holdings"] = None
        try:
            ops = t.funds_data.fund_operations
            raw["fund_ops_expense_ratio"] = float(
                ops.loc["Annual Report Expense Ratio"].iloc[0]
            )
        except Exception:
            raw["fund_ops_expense_ratio"] = None

    return raw


# --------------------------------------------------------------------------
# Normalization → the stable JSONB shape stored in ticker_fundamentals.data
# --------------------------------------------------------------------------


def _epoch_to_iso_date(v: Any) -> str | None:
    if isinstance(v, (int, float)) and math.isfinite(v) and v > 0:
        return datetime.fromtimestamp(v, tz=timezone.utc).date().isoformat()
    return None


def _as_iso_date(v: Any) -> str | None:
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return None


def _pct(v: Any) -> float | None:
    """Fraction → percent (yfinance reports growth/margins/ratios as fractions)."""
    n = _num(v)
    return round(n * 100, 2) if n is not None else None


def _normalize_fundamentals(ticker: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Reshape a raw fetch into the stored payload. Every key is optional —
    yfinance field availability drifts across versions and instrument types."""
    info: dict[str, Any] = raw.get("info") or {}
    calendar: dict[str, Any] = raw.get("calendar") or {}
    quote_type = info.get("quoteType")

    forward_pe = _num(info.get("forwardPE"))
    earnings_growth_pct = _pct(info.get("earningsGrowth"))
    market_cap = _num(info.get("marketCap"))
    free_cashflow = _num(info.get("freeCashflow"))

    # $/share/yr — the unambiguous dividend figure. ETFs usually lack
    # dividendRate but report trailingAnnualDividendRate.
    dividend_rate = _num(info.get("dividendRate"))
    if dividend_rate is None:
        dividend_rate = _num(info.get("trailingAnnualDividendRate"))

    ex_div = _epoch_to_iso_date(info.get("exDividendDate")) or _as_iso_date(
        calendar.get("Ex-Dividend Date")
    )

    earnings_dates = [
        d for d in (_as_iso_date(v) for v in calendar.get("Earnings Date") or []) if d
    ]

    beta = _num(info.get("beta"))

    data: dict[str, Any] = {
        "ticker": ticker,
        "quote_type": quote_type,
        "profile": {
            "name": info.get("longName") or info.get("shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "currency": info.get("currency"),
            "market_cap": market_cap,
        },
        "valuation": {
            "trailing_pe": _num(info.get("trailingPE")),
            "forward_pe": forward_pe,
            "peg": peg_ratio(forward_pe, earnings_growth_pct),
            "price_to_sales": _num(info.get("priceToSalesTrailing12Months")),
            "price_to_book": _num(info.get("priceToBook")),
            "ev_to_ebitda": _num(info.get("enterpriseToEbitda")),
            "price_to_fcf": price_to_fcf(market_cap, free_cashflow),
        },
        "growth": {
            "revenue_growth_pct": _pct(info.get("revenueGrowth")),
            "earnings_growth_pct": earnings_growth_pct,
        },
        "profitability": {
            "gross_margin_pct": _pct(info.get("grossMargins")),
            "operating_margin_pct": _pct(info.get("operatingMargins")),
            "net_margin_pct": _pct(info.get("profitMargins")),
            "roe_pct": _pct(info.get("returnOnEquity")),
        },
        "financial_health": {
            # Yahoo reports total-debt/equity as a percentage (176.3); store
            # the conventional ratio.
            "debt_to_equity": (
                round(_num(info.get("debtToEquity")) / 100, 2)
                if _num(info.get("debtToEquity")) is not None
                else None
            ),
            "current_ratio": _num(info.get("currentRatio")),
        },
        "dividends": {
            "dividend_rate": dividend_rate,
            "payout_ratio_pct": _pct(info.get("payoutRatio")),
            "ex_dividend_date": ex_div,
        },
        "price_action": {
            "high_52w": _num(info.get("fiftyTwoWeekHigh")),
            "low_52w": _num(info.get("fiftyTwoWeekLow")),
            "beta": beta,
            "beta_source": "yahoo" if beta is not None else None,
            "avg_50d": _num(info.get("fiftyDayAverage")),
            "avg_200d": _num(info.get("twoHundredDayAverage")),
            "analyst_target": _num(info.get("targetMeanPrice")),
            "analyst_rating": info.get("recommendationKey"),
            "analyst_rating_mean": _num(info.get("recommendationMean")),
            "analyst_count": _num(info.get("numberOfAnalystOpinions")),
            "short_pct_of_float": _pct(info.get("shortPercentOfFloat")),
        },
        "earnings_dates": earnings_dates,
        "etf": None,
    }

    if quote_type == "ETF":
        # netExpenseRatio arrives already in percent (SPY → 0.0945); the
        # funds_data fallback is a fraction, hence the *100.
        expense = _num(info.get("netExpenseRatio"))
        if expense is None:
            expense = _pct(raw.get("fund_ops_expense_ratio"))
        data["etf"] = {
            "expense_ratio_pct": expense,
            "total_assets": _num(info.get("totalAssets")),
            "category": info.get("category"),
            "fund_family": info.get("fundFamily"),
            "top_holdings": [
                {
                    "symbol": h["symbol"],
                    "name": h["name"],
                    "weight_pct": round(h["weight"] * 100, 2),
                }
                for h in raw.get("top_holdings") or []
            ],
        }

    return data


def core_metrics(
    data: dict[str, Any], last_price: float | None, today: date
) -> dict[str, Any]:
    """The dashboard-column subset, with the serve-time computed fields
    (yield and 52w-distance need the live price; next earnings needs today)."""
    valuation = data.get("valuation") or {}
    dividends = data.get("dividends") or {}
    price_action = data.get("price_action") or {}
    etf = data.get("etf") or {}
    return {
        "quote_type": data.get("quote_type"),
        "forward_pe": valuation.get("forward_pe"),
        "peg": valuation.get("peg"),
        "dividend_yield_pct": dividend_yield_pct(
            dividends.get("dividend_rate"), last_price
        ),
        "pct_from_52w_high": pct_from_52w_high(last_price, price_action.get("high_52w")),
        "next_earnings_date": next_earnings_date(data.get("earnings_dates"), today),
        "beta": price_action.get("beta"),
        "expense_ratio_pct": etf.get("expense_ratio_pct"),
    }


# --------------------------------------------------------------------------
# Cache orchestration (in-process → ticker_fundamentals table → yfinance)
# --------------------------------------------------------------------------


async def _bench_history(benchmark: str) -> list[dict[str, Any]]:
    cached = _bench_cache.get(benchmark)
    if cached and _clock() - cached[0] < BENCH_TTL_SECONDS:
        return cached[1]
    rows = await asyncio.to_thread(market._fetch_history_raw, benchmark, 365)
    _bench_cache[benchmark] = (_clock(), rows)
    return rows


async def _fetch_and_store(ticker: str, repo: Any, settings: Any) -> dict[str, Any] | None:
    """Fetch, normalize, apply the computed-beta fallback, persist.

    Failures persist an error row (short TTL) so a dead ticker isn't
    re-fetched on every page load. Returns the data dict, or None on failure.
    """
    try:
        raw = await asyncio.to_thread(_fetch_fundamentals_raw, ticker)
        data = _normalize_fundamentals(ticker, raw)
    except Exception as exc:  # noqa: BLE001 - recorded, never breaks a page
        await repo.upsert_ticker_fundamentals(
            ticker=ticker, quote_type=None, data={}, fetch_error=str(exc)[:500]
        )
        return None

    if data["price_action"]["beta"] is None and data["quote_type"] in ("EQUITY", "ETF"):
        try:
            asset_rows, bench_rows = await asyncio.gather(
                asyncio.to_thread(market._fetch_history_raw, ticker, 365),
                _bench_history(settings.fundamentals_beta_benchmark),
            )
            beta = beta_from_closes(asset_rows, bench_rows)
            if beta is not None:
                data["price_action"]["beta"] = beta
                data["price_action"]["beta_source"] = "computed"
        except Exception:  # noqa: BLE001 - beta stays None
            pass

    await repo.upsert_ticker_fundamentals(
        ticker=ticker, quote_type=data.get("quote_type"), data=data, fetch_error=None
    )
    _mem_cache[ticker] = (_clock(), data)
    return data


def _spawn_refresh(ticker: str, repo: Any, settings: Any) -> None:
    """Background stale-while-revalidate refresh, deduped per ticker."""
    if ticker in _refresh_tasks:
        return
    task = asyncio.get_running_loop().create_task(
        _fetch_and_store(ticker, repo, settings)
    )
    _refresh_tasks[ticker] = task
    task.add_done_callback(lambda _t: _refresh_tasks.pop(ticker, None))


async def get_fundamentals(
    tickers: list[str], *, repo: Any, settings: Any
) -> dict[str, dict[str, Any]]:
    """Fundamentals for many tickers, cheapest source first.

    In-process cache → DB rows (fresh: serve; stale: serve immediately and
    refresh in the background) → semaphore-bounded live fetch for tickers
    never seen. A request never blocks on yfinance for a known ticker.
    Tickers with a fresh error row are silently absent from the result.
    """
    normalized = normalize_tickers(tickers)
    now = _clock()
    results: dict[str, dict[str, Any]] = {}
    misses: list[str] = []
    for ticker in normalized:
        cached = _mem_cache.get(ticker)
        if cached and now - cached[0] < MEM_TTL_SECONDS:
            results[ticker] = cached[1]
        else:
            misses.append(ticker)
    if not misses:
        return results

    rows = await repo.get_ticker_fundamentals(misses)
    now_dt = datetime.now(timezone.utc)
    ttl = timedelta(hours=settings.fundamentals_ttl_hours)
    error_ttl = timedelta(hours=settings.fundamentals_error_ttl_hours)

    to_fetch: list[str] = []
    for ticker in misses:
        row = rows.get(ticker)
        if row is None:
            to_fetch.append(ticker)
            continue
        age = now_dt - row.fetched_at
        if row.fetch_error:
            if age >= error_ttl:
                to_fetch.append(ticker)
            continue
        results[ticker] = row.data
        _mem_cache[ticker] = (now, row.data)
        if age >= ttl:
            _spawn_refresh(ticker, repo, settings)

    if to_fetch:
        sem = asyncio.Semaphore(FETCH_CONCURRENCY)

        async def _one(ticker: str) -> tuple[str, dict[str, Any] | None]:
            async with sem:
                return ticker, await _fetch_and_store(ticker, repo, settings)

        for ticker, data in await asyncio.gather(*map(_one, to_fetch)):
            if data is not None:
                results[ticker] = data

    return results


async def run_fundamentals_refresh(repo: Any, settings: Any) -> dict[str, Any]:
    """Nightly job body: re-fetch fundamentals for every held ticker, serially
    with spacing — the one place we deliberately trade latency for not getting
    rate-limited by Yahoo."""
    tickers = await repo.list_distinct_tickers()
    refreshed = 0
    failed = 0
    for i, ticker in enumerate(tickers):
        if i:
            await asyncio.sleep(REFRESH_SPACING_SECONDS)
        data = await _fetch_and_store(ticker, repo, settings)
        if data is None:
            failed += 1
        else:
            refreshed += 1
    return {"tickers": len(tickers), "refreshed": refreshed, "failed": failed}
