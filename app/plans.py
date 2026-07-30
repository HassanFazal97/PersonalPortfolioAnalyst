"""Plan limits, cadence rules, and trial state (Free vs Pro vs Pro trial).

Pricing copy lives on ``/pricing``; these helpers are the enforcement layer.

Trial semantics (``users.trial_ends_at`` migration 017, ``trial_started_at``
migration 024): the no-card Pro trial arms at the user's first successful
portfolio sync (``Repo.maybe_start_trial``), so every trial day is a value
day. While it runs the user is Pro everywhere. When it lapses without a
decision, digests PAUSE for a bounded grace window
(``TRIAL_DECISION_GRACE_DAYS``) — the forced-choice moment — after which the
account silently resumes as plain Free: a Free user receiving Monday digests
is a live upgrade prospect, an indefinitely-paused user is churn. Either
explicit resolution clears ``trial_ends_at`` (paying via the webhook, or
``POST /billing/choose-free``). NULL = no trial state.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.config import DEFAULT_USER_ID, Settings

_OWNER_USER_ID = uuid.UUID(DEFAULT_USER_ID)

# How long a lapsed, undecided trial holds digests before the account
# auto-resumes on the Free cadence.
TRIAL_DECISION_GRACE_DAYS = 7


def _trial_ends_at(user: Any | None) -> datetime | None:
    return getattr(user, "trial_ends_at", None) if user is not None else None


def trial_active(user: Any | None, *, now: datetime | None = None) -> bool:
    ends = _trial_ends_at(user)
    if ends is None:
        return False
    return (now or datetime.now(timezone.utc)) < ends


def trial_decision_pending(user: Any | None, *, now: datetime | None = None) -> bool:
    """Trial lapsed and the user hasn't chosen upgrade-or-Free yet.

    This is the digests-paused state, bounded: past the grace window the
    account is treated as plain Free with no pending decision (no DB write
    needed — every consumer resolves through this function)."""
    ends = _trial_ends_at(user)
    if ends is None or getattr(user, "plan", "free") == "pro":
        return False
    moment = now or datetime.now(timezone.utc)
    return ends <= moment < ends + timedelta(days=TRIAL_DECISION_GRACE_DAYS)


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


def max_watchlist(plan: str, settings: Settings) -> int:
    """Max watched (not necessarily held) tickers for this plan."""
    if plan == "pro":
        return settings.pro_max_watchlist
    return settings.free_max_watchlist
