"""Notable investor trades for the agent surfaces (digest + Pro chat).

Two consumers of the same data and formatting:

- ``build_digest_notable_block``: a deterministic text block the digest
  synthesizer receives alongside investigation findings — fresh disclosed
  trades on the user's held/watched tickers (plus followed investors),
  minus anything a previous digest already surfaced. The pipeline records
  every offered trade in ``notable_trade_digest_mentions`` after the digest
  completes, so a trade is offered to the model exactly once per user.

- ``get_notable_trades``: the Pro chat tool over the same feed.

All facts are copied verbatim from disclosed filings; the model narrates,
it never invents amounts (the informational-not-advice posture).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

DIGEST_LOOKBACK_DAYS = 14
DIGEST_MAX_TRADES = 8
_TYPE_LABEL = {"congress": "Congress", "insider": "Insider", "institution": "Fund"}


def _fmt_usd(value: Any) -> str | None:
    if value is None:
        return None
    v = float(value)
    for bound, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= bound:
            return f"${v / bound:.1f}{suffix}"
    return f"${v:,.0f}"


def _investor_label(investor: Any | None) -> str:
    if investor is None:
        return "Undisclosed filer"
    label = investor.display_name
    kind = _TYPE_LABEL.get(investor.investor_type, investor.investor_type)
    detail = None
    if investor.investor_type == "congress":
        detail = "/".join(p for p in (investor.party, investor.state) if p)
    elif investor.investor_type == "insider":
        detail = ", ".join(
            p for p in (investor.title, investor.company_name) if p
        )
    return f"{label} ({kind}{': ' + detail if detail else ''})"


def format_trade_line(trade: Any, investor: Any | None) -> str:
    """One compact factual line per disclosed trade."""
    who = _investor_label(investor)
    subject = trade.ticker or trade.raw_issuer_name or "unresolved issuer"
    when = trade.transaction_date or trade.filed_date

    if trade.source == "sec_13f":
        value = _fmt_usd(trade.value_usd)
        quarter = trade.quarter_end_date
        return (
            f"- {who} reported a {value or 'undisclosed'} position in {subject} "
            f"(13F, quarter ended {quarter}, filed {trade.filed_date})"
        )

    side = {"buy": "bought", "sell": "sold", "exchange": "exchanged"}.get(
        trade.transaction_type, "transacted in"
    )
    amount = None
    if trade.value_usd is not None:
        amount = _fmt_usd(trade.value_usd)
        if trade.shares is not None and trade.price_per_share is not None:
            amount = f"{amount} ({float(trade.shares):,.0f} sh @ ${float(trade.price_per_share):,.2f})"
    elif trade.amount_range_min is not None:
        hi = _fmt_usd(trade.amount_range_max)
        amount = f"{_fmt_usd(trade.amount_range_min)}{'–' + hi if hi else '+'}"
    return (
        f"- {who} {side} {subject}"
        f"{' — ' + amount if amount else ''} on {when} (filed {trade.filed_date})"
    )


async def _load_investors(repo: Any, trades: list[Any]) -> dict[uuid.UUID, Any]:
    ids = list({t.investor_id for t in trades})
    if not ids:
        return {}
    investors = await repo.get_notable_investors_by_ids(ids)
    if isinstance(investors, dict):
        return investors
    return {inv.id: inv for inv in investors}


async def build_digest_notable_block(
    repo: Any,
    user_id: uuid.UUID,
    *,
    tickers: list[str],
    today: date | None = None,
) -> tuple[str | None, list[uuid.UUID]]:
    """(formatted block, offered trade ids) — (None, []) when nothing fresh."""
    since = (today or date.today()) - timedelta(days=DIGEST_LOOKBACK_DAYS)
    trades = await repo.list_unmentioned_notable_trades(
        user_id, tickers=tickers, since=since, limit=DIGEST_MAX_TRADES
    )
    if not trades:
        return None, []
    investors = await _load_investors(repo, trades)
    lines = [format_trade_line(t, investors.get(t.investor_id)) for t in trades]
    return "\n".join(lines), [t.id for t in trades]


GET_NOTABLE_TRADES_SCHEMA = {
    "name": "get_notable_trades",
    "description": (
        "Recent disclosed trades by notable investors: Congress members "
        "(STOCK Act filings), corporate insiders (SEC Form 4), and major "
        "funds (13F holdings). Use when the user asks what politicians, "
        "insiders, or hedge funds are buying/selling — optionally filtered "
        "to specific tickers. Facts come from public filings; disclosure "
        "lags mean trades are days to weeks old. Never present these as "
        "buy/sell advice."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tickers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional Yahoo-format tickers to filter by.",
            },
            "days": {
                "type": "integer",
                "description": "Filing-date lookback window (default 30, max 365).",
            },
        },
        "additionalProperties": False,
    },
}


async def get_notable_trades(payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
    repo = ctx.repo
    days = min(int(payload.get("days") or 30), 365)
    tickers = [
        str(t).upper() for t in (payload.get("tickers") or []) if isinstance(t, str)
    ]
    trades = await repo.list_notable_trades(
        ticker=tickers[0] if len(tickers) == 1 else None,
        since=date.today() - timedelta(days=days),
        limit=25,
    )
    if len(tickers) > 1:
        trades = [t for t in trades if t.ticker in tickers]
    investors = await _load_investors(repo, trades)
    items = []
    for t in trades:
        inv = investors.get(t.investor_id)
        items.append(
            {
                "investor": inv.display_name if inv else None,
                "investor_type": inv.investor_type if inv else None,
                "ticker": t.ticker,
                "issuer": t.raw_issuer_name,
                "side": t.transaction_type,
                "value_usd": float(t.value_usd) if t.value_usd is not None else None,
                "amount_range": (
                    [
                        float(t.amount_range_min) if t.amount_range_min is not None else None,
                        float(t.amount_range_max) if t.amount_range_max is not None else None,
                    ]
                    if t.amount_range_min is not None
                    else None
                ),
                "transaction_date": t.transaction_date.isoformat() if t.transaction_date else None,
                "filed_date": t.filed_date.isoformat(),
                "source": t.source,
            }
        )
    return {"trades": items, "window_days": days}
