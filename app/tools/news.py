"""search_news tool: Finnhub primary, yfinance ``.news`` fallback.

Both sources are isolated behind sync fetch seams so tests can patch them.
Output is normalized to ``{headline, source, url, published_at, summary}``,
near-duplicate headlines are dropped, and full article text is never returned
(summaries are truncated).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from app.config import get_settings

SUMMARY_MAX_CHARS = 500
_DUP_RATIO = 0.9


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


def _fetch_finnhub_news(
    query: str, lookback_days: int, max_results: int
) -> list[dict[str, Any]]:
    """Company news for ``query`` treated as a symbol, via Finnhub."""
    import finnhub

    settings = get_settings()
    if not settings.finnhub_api_key:
        raise RuntimeError("FINNHUB_API_KEY not configured")
    client = finnhub.Client(api_key=settings.finnhub_api_key)
    to = datetime.now(UTC).date()
    frm = to - timedelta(days=lookback_days)
    items = client.company_news(
        query.upper(), _from=frm.isoformat(), to=to.isoformat()
    )
    return items[: max_results * 3]  # over-fetch; dedupe trims later


def _fetch_yfinance_news(query: str) -> list[dict[str, Any]]:
    """Fallback: yfinance ``.news`` for ``query`` treated as a ticker."""
    import yfinance as yf

    return list(yf.Ticker(query.upper()).news or [])


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

    source = "finnhub"
    normalized: list[dict[str, Any]] = []
    try:
        raw = await asyncio.to_thread(
            _fetch_finnhub_news, query, lookback_days, max_results
        )
        normalized = [_normalize_finnhub(i) for i in raw]
    except Exception:  # noqa: BLE001 - fall back to yfinance
        source = "yfinance"
        raw = await asyncio.to_thread(_fetch_yfinance_news, query)
        normalized = [_normalize_yfinance(i) for i in raw]

    items = _dedupe(normalized, max_results)
    return {"query": query, "source": source, "count": len(items), "items": items}
