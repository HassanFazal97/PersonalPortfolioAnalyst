"""Plan limits and cadence rules (Free vs Pro).

Pricing copy lives on ``/pricing``; these helpers are the enforcement layer.
"""

from __future__ import annotations

from datetime import date

from app.config import Settings


def digest_cadence_due(plan: str, local_date: date) -> bool:
    """Whether this user's plan warrants a digest on ``local_date`` (their TZ).

    Pro: every weekday (Mon–Fri). Free: Mondays only. Weekends never."""
    if local_date.weekday() >= 5:
        return False
    if plan == "pro":
        return True
    return local_date.weekday() == 0


def max_digest_holdings(plan: str, settings: Settings) -> int | None:
    """Max holdings included in a digest; ``None`` = all."""
    if plan == "pro":
        return None
    return settings.free_max_digest_holdings
