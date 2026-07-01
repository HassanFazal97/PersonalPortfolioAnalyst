"""Tool schemas (Anthropic tool-use format) and the async dispatch table.

Description strings are load-bearing — they steer tool selection — and are
copied from PROJECT_SPEC §7. ``send_digest`` is registered in M4 and is
exposed only to digest runs; chat runs get ``CHAT_TOOLS``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.config import Settings
from app.tools import market, news, portfolio


@dataclass
class ToolContext:
    """Passed to every tool. Holds shared handles tools may need."""

    settings: Settings
    repo: Any | None = None


ToolFn = Callable[[dict[str, Any], ToolContext], Awaitable[Any]]


GET_PORTFOLIO_SCHEMA = {
    "name": "get_portfolio",
    "description": (
        "Returns the user's current holdings with live valuations. Always call "
        "this before making any claim about what the user owns or how their "
        "portfolio is performing."
    ),
    "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
}

GET_QUOTE_SCHEMA = {
    "name": "get_quote",
    "description": (
        "Batch snapshot of last price, day change %, previous close, and volume "
        "for one or more tickers. Batch every ticker you need into a single call "
        "rather than calling this repeatedly."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tickers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Yahoo-format tickers, e.g. ['NVDA','SHOP.TO'].",
            }
        },
        "required": ["tickers"],
    },
}

GET_PRICE_HISTORY_SCHEMA = {
    "name": "get_price_history",
    "description": (
        "Daily OHLCV plus computed period return %, max drawdown %, and "
        "annualized volatility for one ticker over a window of days. Do NOT use "
        "for current price — use get_quote."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ticker": {"type": "string"},
            "days": {"type": "integer", "minimum": 5, "maximum": 365},
        },
        "required": ["ticker", "days"],
    },
}

SEARCH_NEWS_SCHEMA = {
    "name": "search_news",
    "description": (
        "Recent, de-duplicated news headlines with short summaries for a query "
        "(usually a ticker or company). Returns headline, source, url, "
        "published_at, and summary. Never returns full article text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "lookback_days": {
                "type": "integer",
                "minimum": 1,
                "maximum": 30,
                "default": 3,
            },
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "default": 8,
            },
        },
        "required": ["query"],
    },
}


# Chat runs expose these four. send_digest (M4) is added to the digest toolset.
CHAT_TOOLS: list[dict[str, Any]] = [
    GET_PORTFOLIO_SCHEMA,
    GET_QUOTE_SCHEMA,
    GET_PRICE_HISTORY_SCHEMA,
    SEARCH_NEWS_SCHEMA,
]

# name -> async callable(payload, ctx)
DISPATCH: dict[str, ToolFn] = {
    "get_portfolio": portfolio.get_portfolio,
    "get_quote": market.get_quote,
    "get_price_history": market.get_price_history,
    "search_news": news.search_news,
}
