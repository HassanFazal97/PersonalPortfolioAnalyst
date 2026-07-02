"""Market-data tools: get_quote and get_price_history.

yfinance is the data source, isolated behind two sync fetch seams
(``_fetch_quote_raw`` / ``_fetch_history_raw``) so tests can patch them and
never hit the network. All derived metrics are computed in Python here — the
model is never asked to do arithmetic.

An in-process 60s TTL cache backs get_quote.
"""

from __future__ import annotations

import asyncio
import math
import time
from typing import Any

from app.tools.tickers import normalize_ticker, normalize_tickers

QUOTE_TTL_SECONDS = 60.0

# ticker -> (monotonic_timestamp, normalized_quote_dict)
_quote_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _clock() -> float:
    return time.monotonic()


def cache_clear() -> None:
    """Test/utility helper to reset the quote cache."""
    _quote_cache.clear()


# --------------------------------------------------------------------------
# Network seams (patched in tests)
# --------------------------------------------------------------------------


def _fetch_quote_raw(ticker: str) -> dict[str, Any]:
    """Return raw quote fields for one ticker via yfinance fast_info."""
    import yfinance as yf

    fi = yf.Ticker(ticker).fast_info

    def pick(*keys: str) -> Any:
        for k in keys:
            try:
                val = fi[k]
            except (KeyError, TypeError):
                val = getattr(fi, k, None)
            if val is not None:
                return val
        return None

    return {
        "last_price": pick("last_price", "lastPrice"),
        "previous_close": pick("previous_close", "previousClose"),
        "volume": pick("last_volume", "lastVolume", "volume"),
    }


def _fetch_history_raw(ticker: str, days: int) -> list[dict[str, Any]]:
    """Return raw daily OHLCV rows (oldest first) via yfinance."""
    import yfinance as yf

    df = yf.Ticker(ticker).history(period=f"{days}d", auto_adjust=False)
    rows: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        rows.append(
            {
                "date": idx.date().isoformat(),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
            }
        )
    return rows


# --------------------------------------------------------------------------
# Pure metric helpers (unit-tested directly)
# --------------------------------------------------------------------------


def period_return_pct(closes: list[float]) -> float | None:
    if len(closes) < 2 or closes[0] == 0:
        return None
    return round((closes[-1] - closes[0]) / closes[0] * 100, 2)


def max_drawdown_pct(closes: list[float]) -> float | None:
    if len(closes) < 2:
        return None
    peak = closes[0]
    worst = 0.0
    for c in closes:
        peak = max(peak, c)
        if peak > 0:
            worst = min(worst, (c - peak) / peak)
    return round(worst * 100, 2)


def annualized_volatility_pct(closes: list[float]) -> float | None:
    if len(closes) < 3:
        return None
    daily = [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1] != 0
    ]
    if len(daily) < 2:
        return None
    mean = sum(daily) / len(daily)
    var = sum((r - mean) ** 2 for r in daily) / (len(daily) - 1)
    return round(math.sqrt(var) * math.sqrt(252) * 100, 2)


def _normalize_quote(ticker: str, raw: dict[str, Any]) -> dict[str, Any]:
    last = raw.get("last_price")
    prev = raw.get("previous_close")
    day_change_pct = None
    if last is not None and prev not in (None, 0):
        day_change_pct = round((last - prev) / prev * 100, 2)
    return {
        "ticker": ticker,
        "last_price": round(last, 4) if last is not None else None,
        "day_change_pct": day_change_pct,
        "previous_close": round(prev, 4) if prev is not None else None,
        "volume": int(raw["volume"]) if raw.get("volume") is not None else None,
    }


# --------------------------------------------------------------------------
# Tool entrypoints
# --------------------------------------------------------------------------


async def get_quote(payload: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    tickers = payload.get("tickers")
    if not isinstance(tickers, list) or not tickers:
        raise ValueError("tickers must be a non-empty array of strings")
    normalized = normalize_tickers(tickers)

    quotes: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    now = _clock()

    for ticker in normalized:
        cached = _quote_cache.get(ticker)
        if cached and now - cached[0] < QUOTE_TTL_SECONDS:
            quotes.append(cached[1])
            continue
        try:
            raw = await asyncio.to_thread(_fetch_quote_raw, ticker)
            quote = _normalize_quote(ticker, raw)
            _quote_cache[ticker] = (_clock(), quote)
            quotes.append(quote)
        except Exception as exc:  # noqa: BLE001 - surfaced to the model
            errors.append({"ticker": ticker, "error": str(exc)})

    return {"quotes": quotes, "errors": errors}


async def get_price_history(payload: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    raw_ticker = payload.get("ticker")
    if not isinstance(raw_ticker, str):
        raise ValueError("ticker must be a string")
    ticker = normalize_ticker(raw_ticker)

    days = payload.get("days")
    if not isinstance(days, int) or not (5 <= days <= 365):
        raise ValueError("days must be an integer between 5 and 365")

    rows = await asyncio.to_thread(_fetch_history_raw, ticker, days)
    closes = [r["close"] for r in rows]

    return {
        "ticker": ticker,
        "days_requested": days,
        "bars_returned": len(rows),
        "period_return_pct": period_return_pct(closes),
        "max_drawdown_pct": max_drawdown_pct(closes),
        "annualized_volatility_pct": annualized_volatility_pct(closes),
        "ohlcv": rows,
    }
