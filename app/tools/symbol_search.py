"""Symbol search: find a stock by ticker or company name.

Yahoo's search API (via ``yf.Search``) is the sole provider — it returns
symbols in Yahoo format, which is how every other layer of the app is keyed,
so any result is guaranteed to load on the stock detail page. The network
call is isolated behind a sync seam (``_search_raw``) so tests can patch it
and never hit the network.

Search is a convenience: failures return an empty list rather than raising.
An in-process 1-hour TTL cache bounds repeated queries (the symbol directory
is effectively static intraday).
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from app.tools.tickers import normalize_ticker

SEARCH_TTL_SECONDS = 3600.0
MAX_RESULTS = 8
MIN_QUERY_LENGTH = 2
_CACHE_MAX_ENTRIES = 512

# Instrument types the stock page can render; drops options, futures, FX etc.
_ALLOWED_QUOTE_TYPES = {"EQUITY", "ETF", "MUTUALFUND", "INDEX"}

# Must stay in sync with the ticker path alphabet in app/main.py — search may
# never surface a symbol the stock endpoints would reject.
_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-^=]{1,12}$")

# lowercased query -> (monotonic_timestamp, normalized results)
_search_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _clock() -> float:
    return time.monotonic()


def cache_clear() -> None:
    """Test/utility helper to reset the search cache."""
    _search_cache.clear()


def _search_raw(query: str, limit: int) -> list[dict[str, Any]]:
    """Return raw Yahoo search quote dicts for a free-text query."""
    import yfinance as yf

    search = yf.Search(
        query,
        max_results=limit,
        news_count=0,
        lists_count=0,
        include_cb=False,
    )
    return list(search.quotes or [])


def _normalize_result(raw: dict[str, Any]) -> dict[str, Any] | None:
    symbol = raw.get("symbol")
    quote_type = (raw.get("quoteType") or "").upper()
    if not symbol or quote_type not in _ALLOWED_QUOTE_TYPES:
        return None
    try:
        symbol = normalize_ticker(str(symbol))
    except ValueError:
        return None
    if not _SYMBOL_RE.fullmatch(symbol):
        return None
    return {
        "symbol": symbol,
        "name": raw.get("shortname") or raw.get("longname") or symbol,
        "exchange": raw.get("exchDisp") or raw.get("exchange"),
        "type": quote_type,
    }


async def search_symbols(query: str, limit: int = MAX_RESULTS) -> list[dict[str, Any]]:
    """Search Yahoo for instruments matching a ticker or company name.

    Returns ``[{symbol, name, exchange, type}]`` (Yahoo-format symbols),
    capped at ``limit``; empty on short queries or any provider failure."""
    q = query.strip()
    if len(q) < MIN_QUERY_LENGTH:
        return []
    limit = max(1, min(limit, MAX_RESULTS))

    key = q.lower()
    cached = _search_cache.get(key)
    if cached and _clock() - cached[0] < SEARCH_TTL_SECONDS:
        return cached[1][:limit]

    try:
        raw_results = await asyncio.to_thread(_search_raw, q, MAX_RESULTS)
    except Exception:  # noqa: BLE001 - search fails open to "no results"
        return []

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_results:
        item = _normalize_result(raw)
        if item is None or item["symbol"] in seen:
            continue
        seen.add(item["symbol"])
        results.append(item)
        if len(results) >= MAX_RESULTS:
            break

    if len(_search_cache) >= _CACHE_MAX_ENTRIES:
        _search_cache.clear()
    _search_cache[key] = (_clock(), results)
    return results[:limit]
