"""search_news tool: Finnhub primary, yfinance ``.news`` fallback.

Both sources are isolated behind sync fetch seams so tests can patch them.
Output is normalized to ``{headline, source, url, published_at, summary}``,
near-duplicate headlines are dropped, and full article text is never returned
(summaries are truncated).
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from app.config import get_settings
from app.tools.tickers import normalize_ticker

SUMMARY_MAX_CHARS = 500
_DUP_RATIO = 0.9

# News moves slower than quotes; a longer TTL lets one morning's investigations
# (and repeated chat calls) share a single fetch per symbol. Mirrors the quote
# cache pattern in ``app/tools/market.py``.
NEWS_TTL_SECONDS = 900.0

# (symbol-candidate signature, lookback_days) -> (monotonic_ts, (normalized, source))
_news_cache: dict[tuple[Any, int], tuple[float, tuple[list[dict[str, Any]], str]]] = {}


def _clock() -> float:
    return time.monotonic()


def cache_clear() -> None:
    """Test/utility helper to reset the news cache."""
    _news_cache.clear()


def _canonical(headline: str) -> str:
    return " ".join(headline.lower().split())


def _is_near_duplicate(headline: str, seen: list[str]) -> bool:
    canon = _canonical(headline)
    for prev in seen:
        if SequenceMatcher(None, canon, prev).ratio() >= _DUP_RATIO:
            return True
    return False


# --------------------------------------------------------------------------
# Network seams (patched in tests)
# --------------------------------------------------------------------------


_TICKER_TOKEN = re.compile(r"^[A-Z]{1,5}(\.[A-Z]{1,3})?$|^[A-Z]{1,5}-[A-Z]$")
_SKIP_TOKENS = frozenset({"STOCK", "SHARE", "SHARES", "NEWS", "TODAY", "PRICE"})


def _finnhub_symbol_candidates(query: str) -> list[str]:
    """Derive ticker symbols to try with Finnhub from a free-text query."""
    candidates: list[str] = []
    for part in query.strip().split()[:4]:
        token = part.strip().upper()
        if token in _SKIP_TOKENS or not _TICKER_TOKEN.match(token):
            continue
        try:
            ticker = normalize_ticker(token)
        except ValueError:
            continue
        candidates.append(ticker)
        if "." in ticker:
            candidates.append(ticker.split(".", 1)[0])
    if not candidates and query.strip():
        head = query.strip().split()[0].upper()
        if _TICKER_TOKEN.match(head):
            candidates.append(head)
    seen: set[str] = set()
    out: list[str] = []
    for sym in candidates:
        if sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def _fetch_finnhub_news(
    query: str, lookback_days: int, max_results: int
) -> list[dict[str, Any]]:
    """Company news for symbols extracted from ``query``, via Finnhub."""
    import finnhub

    settings = get_settings()
    if not settings.finnhub_api_key:
        raise RuntimeError("FINNHUB_API_KEY not configured")
    client = finnhub.Client(api_key=settings.finnhub_api_key)
    to = datetime.now(UTC).date()
    frm = to - timedelta(days=lookback_days)
    date_from, date_to = frm.isoformat(), to.isoformat()

    for symbol in _finnhub_symbol_candidates(query):
        items = client.company_news(symbol, _from=date_from, to=date_to)
        if items:
            return items[: max_results * 3]  # over-fetch; dedupe trims later
    return []


def _fetch_yfinance_news(query: str) -> list[dict[str, Any]]:
    """Fallback: yfinance ``.news`` for the first ticker-like token in ``query``."""
    import yfinance as yf

    symbols = _finnhub_symbol_candidates(query) or [query.strip().upper()]
    for symbol in symbols:
        items = list(yf.Ticker(symbol).news or [])
        if items:
            return items
    return []


# --------------------------------------------------------------------------
# Normalizers
# --------------------------------------------------------------------------


def _iso_from_epoch(epoch: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(epoch), tz=UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _normalize_finnhub(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "headline": (item.get("headline") or "").strip(),
        "source": item.get("source"),
        "url": item.get("url"),
        "published_at": _iso_from_epoch(item.get("datetime")),
        "summary": (item.get("summary") or "")[:SUMMARY_MAX_CHARS],
    }


def _normalize_yfinance(item: dict[str, Any]) -> dict[str, Any]:
    # yfinance news items nest fields under "content" in newer versions.
    content = item.get("content", item)
    published = content.get("pubDate") or _iso_from_epoch(item.get("providerPublishTime"))
    url = None
    if isinstance(content.get("canonicalUrl"), dict):
        url = content["canonicalUrl"].get("url")
    url = url or content.get("link") or item.get("link")
    provider = content.get("provider")
    source = provider.get("displayName") if isinstance(provider, dict) else item.get("publisher")
    return {
        "headline": (content.get("title") or item.get("title") or "").strip(),
        "source": source,
        "url": url,
        "published_at": published,
        "summary": (content.get("summary") or content.get("description") or "")[:SUMMARY_MAX_CHARS],
    }


def _dedupe(items: list[dict[str, Any]], max_results: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen_canon: list[str] = []
    for it in items:
        headline = it.get("headline") or ""
        if not headline:
            continue
        if _is_near_duplicate(headline, seen_canon):
            continue
        seen_canon.append(_canonical(headline))
        out.append(it)
        if len(out) >= max_results:
            break
    return out


# --------------------------------------------------------------------------
# Cached fetch (shared by search_news and the digest prefetch)
# --------------------------------------------------------------------------


def _cache_key(query: str, lookback_days: int) -> tuple[Any, int]:
    """Key by resolved symbol candidates so different phrasings for the same
    ticker share a cache entry; fall back to the normalized raw query."""
    candidates = _finnhub_symbol_candidates(query)
    basis: Any = tuple(candidates) if candidates else query.strip().lower()
    return (basis, lookback_days)


async def _cached_fetch(
    query: str, lookback_days: int, max_results: int
) -> tuple[list[dict[str, Any]], str]:
    """Return (normalized_items, source), served from the TTL cache when warm."""
    key = _cache_key(query, lookback_days)
    cached = _news_cache.get(key)
    if cached and _clock() - cached[0] < NEWS_TTL_SECONDS:
        return cached[1]

    source = "finnhub"
    try:
        raw = await asyncio.to_thread(
            _fetch_finnhub_news, query, lookback_days, max_results
        )
        normalized = [_normalize_finnhub(i) for i in raw]
        if not normalized:
            raise RuntimeError("finnhub returned no articles")
    except Exception:  # noqa: BLE001 - fall back to yfinance
        source = "yfinance"
        raw = await asyncio.to_thread(_fetch_yfinance_news, query)
        normalized = [_normalize_yfinance(i) for i in raw]

    _news_cache[key] = (_clock(), (normalized, source))
    return normalized, source


async def prefetch_news_for_tickers(
    tickers: list[str], lookback_days: int = 3, max_results: int = 8
) -> None:
    """Warm the news cache for every holding in one parallel pass.

    Called once at the start of the digest investigation stage so the 2–4
    sub-agent investigations read hot cache instead of each re-fetching. Failures
    are swallowed per-ticker — prefetch is best-effort, not a correctness gate.
    """
    async def _warm(ticker: str) -> None:
        try:
            await _cached_fetch(ticker, lookback_days, max_results)
        except Exception:  # noqa: BLE001 - best effort; real fetch retries later
            pass

    await asyncio.gather(*(_warm(t) for t in tickers))


def get_cached_news_for_ticker(
    ticker: str, lookback_days: int = 3
) -> list[dict[str, Any]]:
    """Return normalized articles from the in-process cache for a ticker."""
    key = _cache_key(ticker, lookback_days)
    cached = _news_cache.get(key)
    if not cached:
        return []
    if _clock() - cached[0] >= NEWS_TTL_SECONDS:
        return []
    items, _source = cached[1]
    return list(items)


# --------------------------------------------------------------------------
# Tool entrypoint
# --------------------------------------------------------------------------


async def search_news(payload: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")

    lookback_days = payload.get("lookback_days", 3)
    if not isinstance(lookback_days, int) or not (1 <= lookback_days <= 30):
        raise ValueError("lookback_days must be an integer between 1 and 30")

    max_results = payload.get("max_results", 8)
    if not isinstance(max_results, int) or not (1 <= max_results <= 20):
        raise ValueError("max_results must be an integer between 1 and 20")

    classify = payload.get("classify", True)

    normalized, source = await _cached_fetch(query, lookback_days, max_results)
    items = _dedupe(normalized, max_results)

    if classify:
        # Local import avoids a cycle (classify imports config/observability).
        from app.tools.classify import classify_news

        items = await classify_news(items, ctx)

    return {"query": query, "source": source, "count": len(items), "items": items}
