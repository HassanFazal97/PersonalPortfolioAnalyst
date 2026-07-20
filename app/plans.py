"""Plan limits, cadence rules, and trial state (Free vs Pro vs Pro trial).

Pricing copy lives on ``/pricing``; these helpers are the enforcement layer.

Trial semantics (``users.trial_ends_at``, migration 017): new signups get a
no-card Pro trial. While it runs the user is Pro everywhere. When it lapses
without a decision, digests PAUSE (neither cadence) until the user either
upgrades (webhook sets plan='pro' and clears the timestamp) or picks Free
(``POST /billing/choose-free`` clears it). NULL = no trial state.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from app.config import DEFAULT_USER_ID, Settings

_OWNER_USER_ID = uuid.UUID(DEFAULT_USER_ID)


def _trial_ends_at(user: Any | None) -> datetime | None:
    return getattr(user, "trial_ends_at", None) if user is not None else None


def trial_active(user: Any | None, *, now: datetime | None = None) -> bool:
    ends = _trial_ends_at(user)
    if ends is None:
        return False
    return (now or datetime.now(timezone.utc)) < ends


def trial_decision_pending(user: Any | None, *, now: datetime | None = None) -> bool:
    """Trial lapsed and the user hasn't chosen upgrade-or-Free yet.

    This is the digests-paused state; both resolutions clear ``trial_ends_at``
    (paying via the webhook, or choosing Free explicitly)."""
    ends = _trial_ends_at(user)
    if ends is None or getattr(user, "plan", "free") == "pro":
        return False
    return (now or datetime.now(timezone.utc)) >= ends


def effective_plan(user: Any | None, *, now: datetime | None = None) -> str:
    """The plan whose limits apply right now: an active trial counts as pro."""
    if user is None:
        return "free"
    if getattr(user, "plan", "free") == "pro":
        return "pro"
    return "pro" if trial_active(user, now=now) else "free"


def user_plan_and_tz(
    user: Any | None, *, user_id: uuid.UUID, settings: Settings
) -> tuple[str, str]:
    """Resolve (effective plan, timezone) for a user row; the owner defaults
    to pro. Trial users resolve to pro while the trial runs."""
    if user_id == _OWNER_USER_ID and user is None:
        return "pro", settings.tz
    if user is None:
        return "free", settings.tz
    return effective_plan(user), getattr(user, "timezone", settings.tz)


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
