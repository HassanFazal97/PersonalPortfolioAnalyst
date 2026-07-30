"""Canadian risk-free rate from the Bank of Canada Valet API.

Every Sharpe/Sortino number the product shows uses a risk-free rate; a
hard-coded 4% is the kind of detail a serious analyst doesn't get wrong.
The 3-month T-bill yield is fetched once a day by the nightly prices job and
persisted into ``daily_prices`` under a pseudo-ticker, so the request path
never makes a network call for it — risk tools read the stored observation
and fail open to the historical default when the store has nothing (unit
contexts, fresh deployments).

BoC Valet is free, unauthenticated, and Canadian-official:
https://www.bankofcanada.ca/valet/observations/{series}/json
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import httpx

from app.quant.performance import DEFAULT_RISK_FREE_ANNUAL

logger = logging.getLogger(__name__)

# 3-month treasury bill yield, per cent, business-daily.
_BOC_SERIES = "V80691342"
_BOC_URL = (
    f"https://www.bankofcanada.ca/valet/observations/{_BOC_SERIES}/json?recent=1"
)
# Pseudo-ticker in daily_prices; adj_close stores the ANNUAL YIELD IN PERCENT
# (e.g. 4.35), not a price. Underscores keep it outside Yahoo's symbol
# alphabet so it can never collide with a real instrument.
RISK_FREE_TICKER = "CA_TBILL_3M"
# A stored observation older than this is treated as absent (rate moved on).
_STALE_DAYS = 14


async def fetch_boc_tbill_yield() -> tuple[date, float] | None:
    """Latest (observation_date, annual_yield_percent) from BoC Valet, or
    None on any failure. Module-level so tests patch it."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(_BOC_URL)
            resp.raise_for_status()
            observations = resp.json().get("observations") or []
        if not observations:
            return None
        latest = observations[-1]
        return (
            date.fromisoformat(latest["d"]),
            float(latest[_BOC_SERIES]["v"]),
        )
    except Exception:  # noqa: BLE001 - the caller fails open
        logger.warning("BoC t-bill fetch failed", exc_info=True)
        return None


async def sync_risk_free(repo: Any) -> bool:
    """Nightly job step: persist today's observation. Best-effort."""
    observed = await fetch_boc_tbill_yield()
    if observed is None or repo is None:
        return False
    obs_date, yield_pct = observed
    try:
        await repo.upsert_daily_prices(
            RISK_FREE_TICKER, [{"date": obs_date.isoformat(), "adj_close": yield_pct}]
        )
        return True
    except Exception:  # noqa: BLE001
        logger.warning("risk-free upsert failed", exc_info=True)
        return False


async def current_risk_free_annual(repo: Any, settings: Any) -> float:
    """The annual risk-free rate as a decimal (0.0435 for 4.35%).

    Priority: explicit RISK_FREE_RATE_ANNUAL override > fresh stored BoC
    observation > the historical default. Never raises, never fetches."""
    override = float(getattr(settings, "risk_free_rate_annual", 0.0) or 0.0)
    if override > 0:
        return override
    if repo is None:
        return DEFAULT_RISK_FREE_ANNUAL
    try:
        stored = await repo.latest_daily_prices([RISK_FREE_TICKER])
        row = stored.get(RISK_FREE_TICKER)
        if row is not None and (date.today() - row.price_date) <= timedelta(
            days=_STALE_DAYS
        ):
            return float(row.adj_close) / 100.0
    except Exception:  # noqa: BLE001 - fail open to the default
        logger.warning("risk-free read failed", exc_info=True)
    return DEFAULT_RISK_FREE_ANNUAL
