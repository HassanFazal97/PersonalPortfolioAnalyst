"""Best Stocks pipeline stage configuration: tool rosters and per-stage
budgets (the deep-dive ``specialists.py`` pattern — kept as data so the
pipeline stays a generic fan-out)."""

from __future__ import annotations

from app.tools.registry import (
    GET_FUNDAMENTALS_SCHEMA,
    GET_PRICE_HISTORY_SCHEMA,
    GET_QUOTE_SCHEMA,
    SEARCH_NEWS_SCHEMA,
)

# Per-candidate analyst sub-loop (Sonnet): grounds the thesis in the fact
# sheet, uses news for "why now". No web search — search_news is cheaper and
# already signal-tagged.
PICK_ANALYST_TOOLS = [
    SEARCH_NEWS_SCHEMA,
    GET_FUNDAMENTALS_SCHEMA,
    GET_PRICE_HISTORY_SCHEMA,
    GET_QUOTE_SCHEMA,
]
PICK_ANALYST_MAX_ITERATIONS = 5
PICK_ANALYST_MAX_COST_USD = 0.15
# Concurrent analyst sub-loops.
ANALYST_CONCURRENCY = 3
# Hard wall-clock ceilings per sub-run. Budgets bound tokens/iterations but
# not a wedged network read (observed live: one hung Yahoo socket inside an
# analyst's tool call stalled the whole fan-out for an hour) — a timed-out
# stage degrades exactly like a failed one instead of wedging the job.
PICK_ANALYST_TIMEOUT_SECONDS = 420.0
PICKS_CRITIC_TIMEOUT_SECONDS = 420.0
MOVER_TIMEOUT_SECONDS = 90.0

# Adversarial critic re-checks claims with first-party tools only.
PICKS_CRITIC_TOOLS = [
    GET_FUNDAMENTALS_SCHEMA,
    GET_QUOTE_SCHEMA,
    GET_PRICE_HISTORY_SCHEMA,
    SEARCH_NEWS_SCHEMA,
]
PICKS_CRITIC_MAX_ITERATIONS = 8
PICKS_CRITIC_MAX_COST_USD = 0.40

# Movers-why: a single classifier-model call over pre-fetched news (no tool
# loop — the anomaly-narration pattern: cheap model narrates fetched facts).
MOVER_MAX_TOKENS = 400
MOVER_NEWS_LOOKBACK_DAYS = 3
MOVER_NEWS_MAX_RESULTS = 6

# Stop admitting new analyst sub-loops once the anchor budget crosses this
# fraction of the run cap, so verification + synthesis always have headroom.
BUDGET_ADMISSION_CUTOFF = 0.8

# Python-computed calibrated confidence (Stage D). Weights over
# [composite percentile, factor coverage, verification pass rate, model self-read].
CONFIDENCE_WEIGHTS = {
    "composite_percentile": 0.35,
    "factor_coverage": 0.25,
    "verification": 0.25,
    "model_confidence": 0.15,
}
MODEL_CONFIDENCE_MAP = {"high": 1.0, "medium": 0.6, "low": 0.3}
# Any data-gap or freshness flag caps confidence here.
CONFIDENCE_GAP_CAP = 0.6
