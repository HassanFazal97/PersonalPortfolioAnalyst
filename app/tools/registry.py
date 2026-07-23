"""Tool schemas (Anthropic tool-use format) and the async dispatch table.

Description strings are load-bearing — they steer tool selection — and are
copied from PROJECT_SPEC §7. ``send_digest`` is registered in M4 and is
exposed only to digest runs; chat runs get ``CHAT_TOOLS``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.config import Settings
from app.tools import (
    anomalies,
    digest,
    fundamentals,
    market,
    news,
    portfolio,
    portfolio_risk,
    recall,
    risk,
)


@dataclass
class ToolContext:
    """Passed to every tool. Holds shared handles tools may need."""

    settings: Settings
    repo: Any | None = None
    run_id: Any | None = None
    # The user this run acts for; tenant reads/writes scope to it (None = owner).
    user_id: Any | None = None
    # IANA timezone for digest_date (defaults to settings.tz in send_digest).
    timezone: str | None = None
    # Anthropic client + live budget, threaded through so tools that make their
    # own model calls (e.g. news signal classification) log and cost-account
    # against the current run. Optional: absent in unit tests / prefetch.
    client: Any | None = None
    budget: Any | None = None


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
        "published_at, summary, and a signal tag ('warning' for risks, "
        "'opportunity' for positive catalysts, 'neutral' otherwise) with a "
        "0–1 salience score. Never returns full article text."
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
            "classify": {
                "type": "boolean",
                "default": True,
                "description": "Tag each item with a risk/opportunity signal.",
            },
        },
        "required": ["query"],
    },
}


GET_FUNDAMENTALS_SCHEMA = {
    "name": "get_fundamentals",
    "description": (
        "Fundamentals for one or more tickers: valuation (P/E, PEG, P/B, "
        "EV/EBITDA, P/FCF), growth, margins, financial health, dividends "
        "(rate, payout, ex-div date), beta, 52-week range, analyst "
        "rating/target, next earnings date, and ETF expense ratio/top "
        "holdings. Use for any question about valuation, income, quality, or "
        "'is X expensive' — never estimate these numbers from memory. Batch "
        "every ticker into one call."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tickers": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 8,
                "description": "Yahoo-format tickers, e.g. ['NVDA','SHOP.TO'].",
            }
        },
        "required": ["tickers"],
    },
}

GET_PORTFOLIO_RISK_SCHEMA = {
    "name": "get_portfolio_risk",
    "description": (
        "Risk profile of the user's holdings: per-holding portfolio weight, "
        "beta, 90-day return, max drawdown, and annualized volatility, plus "
        "portfolio-level weighted beta, concentration (largest and top-3 "
        "weight), and the most volatile holding. Use for 'how risky is my "
        "portfolio', 'what's my beta', 'am I too concentrated', 'which "
        "holding is most volatile'. All numbers are precomputed — report "
        "them, don't recompute."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tickers": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional subset of holdings to analyze; omit for the "
                    "whole portfolio."
                ),
            }
        },
        "additionalProperties": False,
    },
}

SCAN_ANOMALIES_SCHEMA = {
    "name": "scan_anomalies",
    "description": (
        "Statistical anomaly scan of daily price behaviour: unusually large "
        "one-day moves (rolling z-score), sustained drift from baseline "
        "(CUSUM change-point), and decoupling from the benchmark "
        "(correlation break). Defaults to the user's holdings. Use for "
        "'anything unusual in my portfolio?' or 'is X behaving strangely?'. "
        "Detectors flag statistical behaviour only — pair with search_news "
        "when the user asks why."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tickers": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 8,
                "description": "Optional tickers; omit to scan all holdings.",
            }
        },
        "additionalProperties": False,
    },
}


ANALYZE_PORTFOLIO_RISK_SCHEMA = {
    "name": "analyze_portfolio_risk",
    "description": (
        "Portfolio-LEVEL, matrix-based risk analytics — how the holdings behave "
        "TOGETHER, which a single stock's numbers can't show. Returns true "
        "portfolio volatility (from the holdings' return covariance, not a naive "
        "weighted average), the diversification benefit and ratio, per-holding "
        "RISK contribution vs capital weight (finds hidden concentration — a "
        "holding that is a small % of value but a large % of risk), the "
        "effective number of independent bets, and the most-correlated pairs. "
        "Use for 'how diversified am I really', 'what's actually driving my "
        "risk', 'are my holdings too correlated', 'is my portfolio riskier than "
        "it looks'. Distinct from get_portfolio_risk, which is per-holding only. "
        "All numbers are precomputed — report them, don't recompute. Describe "
        "the risk; never recommend trades."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tickers": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional subset of holdings to analyze; omit for the whole "
                    "portfolio."
                ),
            }
        },
        "additionalProperties": False,
    },
}


RECALL_MEMORY_SCHEMA = {
    "name": "recall_memory",
    "description": (
        "Semantic search over this user's OWN history: past morning digests, "
        "stored news headlines, and your prior chat answers. Use when the user "
        "asks what was previously said or reported — 'what did you tell me "
        "about NVDA last month?', 'have we discussed X before?', 'what was in "
        "my digest last week?'. Returns the most relevant snippets with their "
        "date and source; always cite the snippet's date when you use one. "
        "NOT for current prices or fresh news — use get_quote / search_news."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to look for, in natural language.",
            },
            "tickers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional Yahoo-format tickers to filter by.",
            },
            "date_from": {
                "type": "string",
                "description": "Optional ISO lower bound, e.g. 2026-06-01.",
            },
            "date_to": {
                "type": "string",
                "description": "Optional ISO upper bound.",
            },
            "source_types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["digest", "news", "chat", "alert"],
                },
                "description": "Optional filter by where the memory came from.",
            },
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 12,
                "default": 6,
            },
        },
        "required": ["query"],
    },
}


# Chat runs (and digest investigations) expose these — never send_digest.
CHAT_TOOLS: list[dict[str, Any]] = [
    GET_PORTFOLIO_SCHEMA,
    GET_QUOTE_SCHEMA,
    GET_PRICE_HISTORY_SCHEMA,
    SEARCH_NEWS_SCHEMA,
    GET_FUNDAMENTALS_SCHEMA,
    GET_PORTFOLIO_RISK_SCHEMA,
    SCAN_ANOMALIES_SCHEMA,
]

ESTIMATE_DOWNSIDE_RISK_SCHEMA = {
    "name": "estimate_downside_risk",
    "description": (
        "How much the portfolio could LOSE. Returns Value at Risk and "
        "Conditional VaR (Expected Shortfall) at 95%% and 99%% over 1-day and "
        "1-month horizons in both %% and CAD, the worst realized day/week/month "
        "and max drawdown over ~2 years of history, and beta-scaled market-"
        "shock scenarios (e.g. 'what if the market drops 20%%'). Use for 'how "
        "much could I lose', 'what's my downside', 'what happens in a crash', "
        "'value at risk', 'worst case'. All numbers are precomputed — report "
        "them. These are statistical estimates from history, NOT predictions, "
        "and never a recommendation to trade."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tickers": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional subset of holdings to analyze; omit for the whole "
                    "portfolio."
                ),
            }
        },
        "additionalProperties": False,
    },
}


ASSESS_RISK_ADJUSTED_PERFORMANCE_SCHEMA = {
    "name": "assess_risk_adjusted_performance",
    "description": (
        "Risk-ADJUSTED performance and exposure of the portfolio: Sharpe and "
        "Sortino ratios, annualized return and volatility, tracking error and "
        "information ratio vs the benchmark, portfolio beta, and the sector "
        "exposure breakdown (portfolio weight by sector). Use for 'what's my "
        "Sharpe ratio', 'is my return worth the risk', 'how am I doing vs the "
        "market on a risk-adjusted basis', 'what sectors am I exposed to', 'how "
        "concentrated is my sector mix'. All numbers are precomputed over ~2 "
        "years of history — report them. Descriptive only; never advice."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tickers": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional subset of holdings to analyze; omit for the whole "
                    "portfolio."
                ),
            }
        },
        "additionalProperties": False,
    },
}


PROJECT_PORTFOLIO_OUTCOMES_SCHEMA = {
    "name": "project_portfolio_outcomes",
    "description": (
        "Forward-looking projection of the portfolio. Runs a Monte Carlo "
        "simulation (multivariate, from the holdings' return covariance, zero "
        "assumed drift) to show the range of where the portfolio value could "
        "sit over the next year — p5/p25/p50/p75/p95 in CAD and %, plus the "
        "probability of ending below today's value and 1/3/6/12-month "
        "snapshots. Also returns where the portfolio sits on the risk/return "
        "plane vs the minimum-variance and efficient-frontier reference "
        "portfolios. Use for 'what could my portfolio be worth next year', "
        "'what's my range of outcomes', 'how do I compare to an optimal "
        "portfolio', 'am I on the efficient frontier'. These are STATISTICAL "
        "projections from history, NOT forecasts, and the frontier is a "
        "descriptive reference — never a recommendation to rebalance or trade."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tickers": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional subset of holdings to analyze; omit for the whole "
                    "portfolio."
                ),
            }
        },
        "additionalProperties": False,
    },
}


# Pro-only chat tools. The quant engine (covariance/risk decomposition + tail
# risk + risk-adjusted performance + Monte Carlo/frontier) is the headline Pro
# differentiator and its history fetches are heavier, so — like WEB_SEARCH_TOOL
# — these are appended to the roster only for Pro chats (see
# app/main.py::_prepare_chat).
PRO_CHAT_TOOLS: list[dict[str, Any]] = [
    ANALYZE_PORTFOLIO_RISK_SCHEMA,
    ESTIMATE_DOWNSIDE_RISK_SCHEMA,
    ASSESS_RISK_ADJUSTED_PERFORMANCE_SCHEMA,
    PROJECT_PORTFOLIO_OUTCOMES_SCHEMA,
]

# The synthesize stage exposes ONLY send_digest so the run must terminate by
# delivering the digest.
DIGEST_TOOLS: list[dict[str, Any]] = [digest.SEND_DIGEST_SCHEMA]

# name -> async callable(payload, ctx)
DISPATCH: dict[str, ToolFn] = {
    "get_portfolio": portfolio.get_portfolio,
    "get_quote": market.get_quote,
    "get_price_history": market.get_price_history,
    "search_news": news.search_news,
    "send_digest": digest.send_digest,
    "get_fundamentals": fundamentals.get_fundamentals_tool,
    "get_portfolio_risk": risk.get_portfolio_risk,
    "analyze_portfolio_risk": portfolio_risk.analyze_portfolio_risk,
    "estimate_downside_risk": portfolio_risk.estimate_downside_risk,
    "assess_risk_adjusted_performance": portfolio_risk.assess_risk_adjusted_performance,
    "project_portfolio_outcomes": portfolio_risk.project_portfolio_outcomes,
    "scan_anomalies": anomalies.scan_anomalies,
    "recall_memory": recall.recall_memory,
}

# Tools that fan out to live market-data fetches need more headroom than the
# global settings.tool_timeout_seconds default (10 s).
TOOL_TIMEOUTS: dict[str, float] = {
    "get_fundamentals": 20.0,
    "get_portfolio_risk": 25.0,
    # Fans out ~2yr of adjusted-close history for up to 25 holdings + FX.
    "analyze_portfolio_risk": 35.0,
    # Same fan-out plus the benchmark; the adjusted-close cache makes a
    # back-to-back call with analyze_portfolio_risk cheap.
    "estimate_downside_risk": 35.0,
    # Same fan-out plus a fundamentals read for sector exposure.
    "assess_risk_adjusted_performance": 35.0,
    # Same fan-out plus a 5000-path Monte Carlo and the frontier QP.
    "project_portfolio_outcomes": 40.0,
    "scan_anomalies": 30.0,
    # One Voyage embed round-trip + one indexed pgvector query.
    "recall_memory": 15.0,
}

# Anthropic server-side web search (same tool the macro specialists use).
# Executed by the API, never dispatched locally — appended to CHAT_TOOLS for
# Pro chats only; search cost doesn't fit the Free tier's economics.
WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": 3,
}
