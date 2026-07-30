"""Company logos for the dashboard: ticker -> proxied favicon bytes.

The browser never asks a third party for a holding's logo — per-user
requests to an external icon host would leak the user's positions to that
host. Instead the server resolves the company's website domain from the
globally cached fundamentals profile (see fundamentals.py) and proxies
Google's favicon service, caching bytes in-process so a ticker costs one
outbound fetch per process regardless of how many users hold it.

Fundamentals rows stored before the profile carried ``website`` self-heal:
requesting their logo spawns the standard background refresh and reports a
miss for now, so the next dashboard load has the logo.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.tools import fundamentals
from app.tools.tickers import normalize_ticker

# Redirects to gstatic's faviconV2, which returns a real 404 when it has
# nothing for the domain — misses fall through to the legend's lettermark.
_ICON_URL = "https://www.google.com/s2/favicons?domain={domain}&sz=64"
FETCH_TIMEOUT_SECONDS = 5.0
# Logos change ~never; a long TTL keeps outbound fetches rare without
# pinning a rebrand forever.
CACHE_TTL_SECONDS = 7 * 86400.0
# Misses retry sooner: the website lands on the next fundamentals refresh.
MISS_TTL_SECONDS = 6 * 3600.0

# ticker -> (monotonic_timestamp, (bytes, media_type) | None on a miss)
_cache: dict[str, tuple[float, tuple[bytes, str] | None]] = {}
_fetch_locks: dict[str, asyncio.Lock] = {}


def _clock() -> float:
    return time.monotonic()


def cache_clear() -> None:
    """Test/utility helper to reset the in-process caches."""
    _cache.clear()
    _fetch_locks.clear()


def domain_of(website: Any) -> str | None:
    """Host from a profile website URL ("https://www.te.com/en" -> "te.com")."""
    if not isinstance(website, str) or not website.strip():
        return None
    site = website.strip()
    host = urlsplit(site).netloc or urlsplit("//" + site).netloc
    host = host.rsplit("@", 1)[-1].split(":")[0].lower()
    return host.removeprefix("www.") or None


async def _fetch_icon_raw(domain: str) -> tuple[bytes, str] | None:
    """Network seam (patched in tests): icon bytes + media type, None on 404."""
    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True
    ) as client:
        resp = await client.get(_ICON_URL.format(domain=domain))
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.content, resp.headers.get("content-type", "image/png")


def _fresh(entry: tuple[float, tuple[bytes, str] | None] | None) -> bool:
    if entry is None:
        return False
    ttl = CACHE_TTL_SECONDS if entry[1] is not None else MISS_TTL_SECONDS
    return _clock() - entry[0] < ttl


async def get_logo(
    raw_ticker: str, *, repo: Any, settings: Any
) -> tuple[bytes, str] | None:
    """(bytes, media_type) for the ticker's logo, or None (no site / no icon)."""
    ticker = normalize_ticker(raw_ticker)
    entry = _cache.get(ticker)
    if _fresh(entry):
        return entry[1]

    data = await fundamentals.get_fundamentals([ticker], repo=repo, settings=settings)
    profile = (data.get(ticker) or {}).get("profile") or {}
    if ticker in data and "website" not in profile:
        # Pre-website row: kick the deduped background refresh and miss for
        # now, uncached — a refreshed row always has the key, so the next
        # dashboard load resolves normally instead of waiting out MISS_TTL.
        fundamentals._spawn_refresh(ticker, repo, settings)
        return None
    domain = domain_of(profile.get("website"))
    if domain is None:
        _cache[ticker] = (_clock(), None)
        return None

    lock = _fetch_locks.setdefault(ticker, asyncio.Lock())
    async with lock:
        entry = _cache.get(ticker)  # a concurrent request may have filled it
        if _fresh(entry):
            return entry[1]
        try:
            icon = await _fetch_icon_raw(domain)
        except httpx.HTTPError:
            return None  # transient: uncached, so the next request retries
        _cache[ticker] = (_clock(), icon)
        return icon
