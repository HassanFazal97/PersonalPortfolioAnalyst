"""get_portfolio tool: positions joined with live valuations, totals in CAD.

Reuses ``market.get_quote`` for prices (and its cache) and for the USDCAD=X FX
rate. USD positions are converted to CAD for the totals; the rate used is
reported alongside.
"""

from __future__ import annotations

from typing import Any

from app.tools import market

FX_TICKER = "USDCAD=X"


async def _usdcad_rate() -> float | None:
    result = await market.get_quote({"tickers": [FX_TICKER]})
    for q in result["quotes"]:
        if q["ticker"] == FX_TICKER:
            return q["last_price"]
    return None


def _to_cad(value: float, currency: str, usdcad: float | None) -> float | None:
    if currency == "CAD":
        return value
    if currency == "USD" and usdcad is not None:
        return value * usdcad
    return None  # unknown currency -> excluded from CAD total


async def get_portfolio(payload: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    if ctx is None or getattr(ctx, "repo", None) is None:
        raise RuntimeError("get_portfolio requires database access")

    positions = await ctx.repo.list_positions()
    if not positions:
        return {"positions": [], "totals": {}, "note": "No positions on record."}

    tickers = sorted({p.ticker for p in positions})
    quote_result = await market.get_quote({"tickers": tickers})
    quotes = {q["ticker"]: q for q in quote_result["quotes"]}
    usdcad = await _usdcad_rate()

    out_positions: list[dict[str, Any]] = []
    total_mv_cad = 0.0
    total_cost_cad = 0.0
    any_unpriced = False

    for p in positions:
        quantity = float(p.quantity)
        avg_cost = float(p.avg_cost)
        q = quotes.get(p.ticker)
        last_price = q["last_price"] if q else None

        row: dict[str, Any] = {
            "ticker": p.ticker,
            "quantity": quantity,
            "avg_cost": avg_cost,
            "currency": p.currency,
            "account": p.account,
            "last_price": last_price,
            "day_change_pct": q["day_change_pct"] if q else None,
        }

        if last_price is not None:
            market_value = quantity * last_price
            cost_basis = quantity * avg_cost
            unrealized_pnl = market_value - cost_basis
            row["market_value"] = round(market_value, 2)
            row["unrealized_pnl"] = round(unrealized_pnl, 2)
            row["unrealized_pnl_pct"] = (
                round((last_price / avg_cost - 1) * 100, 2) if avg_cost else None
            )
            mv_cad = _to_cad(market_value, p.currency, usdcad)
            cost_cad = _to_cad(cost_basis, p.currency, usdcad)
            if mv_cad is not None and cost_cad is not None:
                total_mv_cad += mv_cad
                total_cost_cad += cost_cad
            else:
                any_unpriced = True
        else:
            row["market_value"] = None
            row["unrealized_pnl"] = None
            row["unrealized_pnl_pct"] = None
            row["error"] = "quote unavailable"
            any_unpriced = True

        out_positions.append(row)

    totals = {
        "total_market_value_cad": round(total_mv_cad, 2),
        "total_cost_basis_cad": round(total_cost_cad, 2),
        "total_unrealized_pnl_cad": round(total_mv_cad - total_cost_cad, 2),
        "total_unrealized_pnl_pct": (
            round((total_mv_cad / total_cost_cad - 1) * 100, 2)
            if total_cost_cad
            else None
        ),
        "usdcad_rate": usdcad,
        "includes_all_positions": not any_unpriced,
    }

    return {"positions": out_positions, "totals": totals}
