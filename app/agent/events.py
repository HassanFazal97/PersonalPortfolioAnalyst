"""Agent progress events — the optional callback seam on ``run_agent``.

Events are plain dicts with a ``type`` key so they JSON-serialize straight
into SSE frames. The callback is fire-and-forget from the loop's point of
view: a dead consumer (closed browser tab, full queue) must never abort a
run, so ``emit`` swallows and logs callback exceptions.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

AgentEvent = dict[str, Any]
EventCallback = Callable[[AgentEvent], Awaitable[None]]

# Friendly labels shown in the chat UI while a tool runs. Unlisted tools fall
# back to "Running <name>…" so new tools degrade gracefully.
TOOL_LABELS: dict[str, str] = {
    "get_portfolio": "Reading your portfolio",
    "get_quote": "Fetching live quotes",
    "get_price_history": "Analyzing price history",
    "search_news": "Scanning the news",
    "get_fundamentals": "Pulling fundamentals",
    "get_portfolio_risk": "Measuring portfolio risk",
    "scan_anomalies": "Scanning for anomalies",
    "recall_memory": "Searching past conversations",
    "web_search": "Searching the web",
    "send_digest": "Composing your digest",
}


def tool_label(name: str) -> str:
    return TOOL_LABELS.get(name, f"Running {name}")


async def emit(cb: EventCallback | None, event: AgentEvent) -> None:
    """Deliver one event to the callback; never raise into the agent loop."""
    if cb is None:
        return
    try:
        await cb(event)
    except Exception:
        logger.warning("agent event callback failed", exc_info=True)
