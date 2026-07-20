"""Per-user context injected into the chat system prompt.

A cheap sibling of the digest pipeline's ``build_market_context``: one
portfolio read (quotes come from the shared 60s cache) and one digest lookup —
no per-ticker history calls. The blob keeps the model grounded in what the
user actually holds and usually saves it a get_portfolio round-trip.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.tools import portfolio
from app.tools.registry import ToolContext

logger = logging.getLogger(__name__)

# Keep the injected blob small: it is resent on every loop iteration.
DIGEST_SNIPPET_CHARS = 400
MAX_POSITIONS = 25


async def build_chat_context(ctx: ToolContext, *, tz: str) -> str:
    """A compact JSON context blob, or "" when nothing could be gathered.

    Never raises: chat must still work when quotes or the DB hiccup.
    """
    context: dict[str, Any] = {}
    try:
        now_local = datetime.now(ZoneInfo(tz))
    except Exception:  # noqa: BLE001 - bad stored timezone
        now_local = datetime.now()
    context["today"] = now_local.strftime("%A %Y-%m-%d %H:%M %Z").strip()

    try:
        pf = await portfolio.get_portfolio({}, ctx)
        positions = [
            {
                "ticker": p["ticker"],
                "quantity": p["quantity"],
                "currency": p.get("currency"),
                "market_value": p.get("market_value"),
                "day_change_pct": p.get("day_change_pct"),
            }
            for p in (pf.get("positions") or [])[:MAX_POSITIONS]
        ]
        context["positions"] = positions
        totals = pf.get("totals") or {}
        context["totals"] = {
            "total_market_value_cad": totals.get("total_market_value_cad"),
            "total_unrealized_pnl_cad": totals.get("total_unrealized_pnl_cad"),
            "usdcad_rate": totals.get("usdcad_rate"),
        }
    except Exception:  # noqa: BLE001
        logger.warning("chat context: portfolio unavailable", exc_info=True)

    try:
        repo = ctx.repo
        if repo is not None:
            today = now_local.date()
            digest = await repo.get_digest(today, user_id=ctx.user_id)
            digest_date = today
            if digest is None:
                digest_date = today - timedelta(days=1)
                digest = await repo.get_digest(digest_date, user_id=ctx.user_id)
            if digest is not None and getattr(digest, "body", None):
                context["latest_digest"] = {
                    "date": digest_date.isoformat(),
                    "snippet": digest.body[:DIGEST_SNIPPET_CHARS],
                }
    except Exception:  # noqa: BLE001
        logger.warning("chat context: digest lookup failed", exc_info=True)

    if not context.get("positions") and "latest_digest" not in context:
        # Date alone isn't worth the tokens (the prompt already states the tz).
        return ""
    return json.dumps(context, default=str)


def compose_chat_system_prompt(base_prompt: str, context: str) -> str:
    """The chat system prompt with the user-context blob appended."""
    if not context:
        return base_prompt
    return (
        f"{base_prompt}\n\n<user_context>\n{context}\n</user_context>\n"
        "The user_context block is a snapshot taken just before this "
        "conversation turn — use it for orientation, but still call tools "
        "for any number you present as current."
    )
