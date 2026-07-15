"""Aggregation math for price-anomaly alerts (ported from Shizen's
SynthesisAgent rule — "no LLM judgment in the gate").

Pure functions, no I/O. One user gets ONE alert per scan regardless of how
many holdings flagged: per-ticker max severity, combined via noisy-OR

    S = 1 − ∏(1 − sᵢ)

the probability that *something* is anomalous given independent per-ticker
evidence. Shizen's min_streams>=2 escalation gate is deliberately dropped —
for a portfolio product a single 3σ move in *your* holding is alert-worthy;
the per-detector thresholds already gated.
"""

from __future__ import annotations

import hashlib
from datetime import date
from functools import reduce
from typing import Iterable

from .scanner import AnomalyFlag

CATEGORY = "price_anomaly"


def noisy_or(severities: Iterable[float]) -> float:
    sevs = list(severities)
    if not sevs:
        return 0.0
    return 1.0 - reduce(lambda acc, s: acc * (1.0 - s), sevs, 1.0)


def best_flag_per_ticker(flags: list[AnomalyFlag]) -> dict[str, AnomalyFlag]:
    """Max-severity flag per ticker (the per-stream reduction from Shizen)."""
    best: dict[str, AnomalyFlag] = {}
    for flag in flags:
        cur = best.get(flag.ticker)
        if cur is None or flag.severity > cur.severity:
            best[flag.ticker] = flag
    return best


def severity_label(s: float) -> str:
    """Map combined severity onto the alerts.severity text values."""
    if s >= 0.85:
        return "high"
    if s >= 0.6:
        return "medium"
    return "low"


def build_fingerprint(scan_date: date, flags: list[AnomalyFlag]) -> str:
    """Stable per-day event hash.

    Includes the scan date so same-day re-runs dedup via the schema's
    UNIQUE(user_id, fingerprint) while a new spike next week re-alerts; the
    cross-day fatigue control is the per-ticker cooldown, not the fingerprint.
    """
    parts = sorted(f"{f.ticker}.{f.detector}.{f.direction}" for f in flags)
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
    return f"{CATEGORY}:{scan_date.isoformat()}:{digest}"


def _describe(flag: AnomalyFlag) -> str:
    if flag.detector == "zscore":
        move = f"{flag.day_change_pct:+.1f}%" if flag.day_change_pct is not None else ""
        return f"{flag.ticker} {move} today ({abs(flag.score):.1f}σ move)".replace("  ", " ")
    if flag.detector == "cusum":
        trend = "climbing" if flag.direction == "up" else "sliding"
        return f"{flag.ticker} has been steadily {trend} vs its recent baseline"
    return f"{flag.ticker} has decoupled from its benchmark"


def format_fallback_message(
    flags: list[AnomalyFlag], combined: float
) -> tuple[str, str]:
    """Deterministic (headline, body) used when Haiku narration fails.

    The alert must still fire — math already decided it matters. Body stays
    within the alerts table's ≤300-char convention.
    """
    best = best_flag_per_ticker(flags)
    tickers = sorted(best)
    if len(tickers) == 1:
        headline = f"Unusual move in {tickers[0]}"
    else:
        headline = f"Unusual moves in {len(tickers)} holdings: {', '.join(tickers[:4])}"
        if len(tickers) > 4:
            headline += ", …"
    lines = [_describe(best[t]) for t in tickers[:4]]
    if len(tickers) > 4:
        lines.append(f"(+{len(tickers) - 4} more)")
    body = "; ".join(lines)
    if len(body) > 290:
        body = body[:287] + "…"
    return headline, body
