"""get_portfolio_risk tool: per-holding and portfolio-level risk metrics.

Composes math that already exists elsewhere — betas from the fundamentals
cache (with its computed-beta fallback), return/drawdown/volatility from
market.py's helpers over a 90-day window, weights from get_portfolio's CAD
valuations — so the model never has to derive a number itself.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.tools import fundamentals, market, portfolio
from app.tools.tickers import normalize_tickers

HISTORY_DAYS = 90
# Bound live history fetches per call; beyond this the largest positions win.
MAX_TICKERS = 10
_FETCH_CONCURRENCY = 3


def _history_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [float(r["close"]) for r in rows]
    return {
        "period_return_pct": market.period_return_pct(closes),
        "max_drawdown_pct": market.max_drawdown_pct(closes),
        "annualized_volatility_pct": market.annualized_volatility_pct(closes),
    }


async def get_portfolio_risk(payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
    if ctx is None or getattr(ctx, "repo", None) is None:
        raise RuntimeError("get_portfolio_risk requires database access")

    pf = await portfolio.get_portfolio({}, ctx)
    positions = pf.get("positions") or []
    if not positions:
        return {"holdings": [], "portfolio": {}, "note": "No positions on record."}

    requested = payload.get("tickers")
    if requested:
        wanted = set(normalize_tickers(requested))
        positions = [p for p in positions if p["ticker"] in wanted]
        if not positions:
            return {
                "holdings": [],
                "portfolio": {},
                "note": "None of the requested tickers are in the portfolio.",
            }

    usdcad = (pf.get("totals") or {}).get("usdcad_rate")

    # Collapse per-account rows into one bucket per ticker, in CAD so USD and
    # CAD positions weigh comparably.
    mv_by_ticker: dict[str, float] = {}
    for p in positions:
        mv = p.get("market_value")
        if mv is None:
            continue
        mv_cad = portfolio._to_cad(mv, p.get("currency") or "CAD", usdcad)
        if mv_cad is None:
            continue
        mv_by_ticker[p["ticker"]] = mv_by_ticker.get(p["ticker"], 0.0) + mv_cad

    if not mv_by_ticker:
        return {
            "holdings": [],
            "portfolio": {},
            "note": "No priceable positions to analyze.",
        }

    ranked = sorted(mv_by_ticker, key=mv_by_ticker.get, reverse=True)
    tickers = ranked[:MAX_TICKERS]
    skipped = ranked[MAX_TICKERS:]
    total_mv = sum(mv_by_ticker[t] for t in tickers)

    funds = await fundamentals.get_fundamentals(
        tickers, repo=ctx.repo, settings=ctx.settings
    )

    sem = asyncio.Semaphore(_FETCH_CONCURRENCY)

    async def _one(ticker: str) -> tuple[str, dict[str, Any] | None]:
        async with sem:
            try:
                rows = await asyncio.to_thread(
                    market._fetch_history_raw, ticker, HISTORY_DAYS
                )
                return ticker, _history_metrics(rows)
            except Exception:  # noqa: BLE001 - one bad ticker never kills the scan
                return ticker, None

    history = dict(await asyncio.gather(*map(_one, tickers)))

    holdings: list[dict[str, Any]] = []
    weighted_beta_sum = 0.0
    beta_weight_covered = 0.0
    for ticker in tickers:
        weight_pct = round(mv_by_ticker[ticker] / total_mv * 100, 2) if total_mv else None
        price_action = (funds.get(ticker) or {}).get("price_action") or {}
        beta = price_action.get("beta")
        metrics = history.get(ticker)
        row: dict[str, Any] = {
            "ticker": ticker,
            "weight_pct": weight_pct,
            "beta": beta,
            "beta_source": price_action.get("beta_source"),
        }
        row.update(
            metrics
            or {
                "period_return_pct": None,
                "max_drawdown_pct": None,
                "annualized_volatility_pct": None,
                "error": "history unavailable",
            }
        )
        holdings.append(row)
        if beta is not None and weight_pct is not None:
            weighted_beta_sum += beta * weight_pct
            beta_weight_covered += weight_pct

    weights = sorted(
        (h["weight_pct"] for h in holdings if h["weight_pct"] is not None),
        reverse=True,
    )
    vols = [
        (h["annualized_volatility_pct"], h["ticker"])
        for h in holdings
        if h["annualized_volatility_pct"] is not None
    ]
    portfolio_level: dict[str, Any] = {
        "window_days": HISTORY_DAYS,
        # Weighted by the value each beta actually covers, so a missing beta
        # dilutes coverage instead of silently skewing the average.
        "weighted_beta": (
            round(weighted_beta_sum / beta_weight_covered, 2)
            if beta_weight_covered
            else None
        ),
        "beta_coverage_pct": round(beta_weight_covered, 2) if holdings else None,
        "largest_position_pct": weights[0] if weights else None,
        "top3_concentration_pct": round(sum(weights[:3]), 2) if weights else None,
        "most_volatile": (
            {"ticker": max(vols)[1], "annualized_volatility_pct": max(vols)[0]}
            if vols
            else None
        ),
    }

    out: dict[str, Any] = {"holdings": holdings, "portfolio": portfolio_level}
    if skipped:
        out["note"] = (
            f"Analyzed the {MAX_TICKERS} largest positions; skipped: "
            f"{', '.join(skipped)}."
        )
    return out
