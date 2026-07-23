"""The deep-dive specialist roster: who researches what, with which tools,
under what budget. Kept as data so the pipeline stays a generic fan-out."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent.prompts import DEEP_DIVE_SPECIALIST_PROMPTS
from app.tools.registry import (
    ANALYZE_PORTFOLIO_RISK_SCHEMA,
    GET_FUNDAMENTALS_SCHEMA,
    GET_PORTFOLIO_RISK_SCHEMA,
    GET_PORTFOLIO_SCHEMA,
    GET_PRICE_HISTORY_SCHEMA,
    GET_QUOTE_SCHEMA,
    SCAN_ANOMALIES_SCHEMA,
    SEARCH_NEWS_SCHEMA,
    WEB_SEARCH_TOOL,
)


@dataclass(frozen=True)
class Specialist:
    name: str
    label: str  # shown in the progress UI
    system_prompt: str
    tools: list[dict[str, Any]]
    max_iterations: int
    max_cost_usd: float


# Deep dives are Pro-only, so the Pro-gated tools (web search, the quant
# engine) are always available to the specialists that want them.
ROSTER: list[Specialist] = [
    Specialist(
        name="fundamentals",
        label="Fundamentals analyst",
        system_prompt=DEEP_DIVE_SPECIALIST_PROMPTS["fundamentals"],
        tools=[GET_PORTFOLIO_SCHEMA, GET_FUNDAMENTALS_SCHEMA, GET_QUOTE_SCHEMA],
        max_iterations=6,
        max_cost_usd=0.15,
    ),
    Specialist(
        name="technical",
        label="Technical analyst",
        system_prompt=DEEP_DIVE_SPECIALIST_PROMPTS["technical"],
        tools=[
            GET_PORTFOLIO_SCHEMA,
            GET_PRICE_HISTORY_SCHEMA,
            GET_QUOTE_SCHEMA,
            SCAN_ANOMALIES_SCHEMA,
        ],
        max_iterations=6,
        max_cost_usd=0.15,
    ),
    Specialist(
        name="risk",
        label="Risk analyst",
        system_prompt=DEEP_DIVE_SPECIALIST_PROMPTS["risk"],
        tools=[
            GET_PORTFOLIO_SCHEMA,
            GET_PORTFOLIO_RISK_SCHEMA,
            ANALYZE_PORTFOLIO_RISK_SCHEMA,
            GET_PRICE_HISTORY_SCHEMA,
        ],
        max_iterations=5,
        max_cost_usd=0.15,
    ),
    Specialist(
        name="news_macro",
        label="News & macro analyst",
        system_prompt=DEEP_DIVE_SPECIALIST_PROMPTS["news_macro"],
        tools=[GET_PORTFOLIO_SCHEMA, SEARCH_NEWS_SCHEMA, WEB_SEARCH_TOOL],
        max_iterations=8,
        max_cost_usd=0.25,
    ),
]

# The critic re-checks claims with the full internal toolset (no web search:
# verification must be against first-party data, and it keeps the stage cheap).
CRITIC_TOOLS: list[dict[str, Any]] = [
    GET_PORTFOLIO_SCHEMA,
    GET_QUOTE_SCHEMA,
    GET_PRICE_HISTORY_SCHEMA,
    GET_FUNDAMENTALS_SCHEMA,
    GET_PORTFOLIO_RISK_SCHEMA,
    ANALYZE_PORTFOLIO_RISK_SCHEMA,
    SCAN_ANOMALIES_SCHEMA,
]
CRITIC_MAX_ITERATIONS = 6
CRITIC_MAX_COST_USD = 0.20
