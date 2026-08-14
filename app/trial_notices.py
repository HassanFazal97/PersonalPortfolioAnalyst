"""Trial lifecycle notices: T-2 days, day-of-lapse, and +3 days undecided.

The trial funnel's biggest hole was silence: the trial ended, digests paused,
and nothing told the user. This job scans users with live trial state once a
day and queues at most three messages per account through the existing
delivery queue (preferred-channel resolution, CASL unsubscribe handling, and
channel-aware short/long bodies all come free from ``enqueue_outbound``).

Dedup is by payload kind via ``has_outbound_of_kind`` — an account gets one
trial, so each notice sends at most once ever. Long-lapsed accounts (past the
decision grace window, e.g. anyone predating this job) get nothing: a "your
trial just ended" message months late reads as a bug, and the win-back
campaign (roadmap Phase 3) is the right channel for them.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from app.plans import TRIAL_DECISION_GRACE_DAYS, trial_active

logger = logging.getLogger(__name__)

# Send the heads-up when this much (or less) of the trial remains.
ENDING_SOON_DAYS = 2
# Send the last-chance nudge this long after an undecided lapse.
FINAL_NUDGE_DAYS = 3


def _upgrade_url(settings: Any) -> str:
    base = (settings.public_base_url or "").rstrip("/")
    return f"{base}/app/settings?billing=upgrade" if base else "the settings page"


def _notices_for(user: Any, now: datetime, settings: Any) -> list[dict[str, str]]:
    """The notices this user is due, oldest-first (kind/subject/body/sms)."""
    ends = user.trial_ends_at
    url = _upgrade_url(settings)
    out: list[dict[str, str]] = []
    if trial_active(user, now=now):
        days_left = max(1, math.ceil((ends - now) / timedelta(days=1)))
        if days_left <= ENDING_SOON_DAYS:
            plural = "s" if days_left != 1 else ""
            out.append(
                {
                    "kind": "trial_ending",
                    "subject": f"Your Pro trial ends in {days_left} day{plural}",
                    "body": (
                        f"Your Cirvia Pro trial ends in {days_left} day{plural}. "
                        "After that, daily digests, Top Picks, Deep Dives, and the "
                        "Risk Lab pause until you pick a plan: upgrade to keep "
                        f"them, or continue free with a Monday digest.\n\n{url}"
                    ),
                    "sms": (
                        f"Cirvia: your Pro trial ends in {days_left} day{plural}. "
                        f"Keep daily digests + picks, or go free: {url}"
                    ),
                }
            )
        return out
    lapsed_for = now - ends
    if lapsed_for >= timedelta(days=TRIAL_DECISION_GRACE_DAYS):
        return out
    out.append(
        {
            "kind": "trial_ended",
            "subject": "Your Pro trial has ended: pick a plan",
            "body": (
                "Your Cirvia Pro trial has ended, so your digests are paused. "
                "Upgrade to Pro to resume daily briefings, Top Picks, Deep "
                "Dives, and the Risk Lab, or choose Free and keep a Monday "
                f"digest on your top holdings.\n\n{url}"
            ),
            "sms": f"Cirvia: your Pro trial ended, digests are paused. Pick a plan: {url}",
        }
    )
    if lapsed_for >= timedelta(days=FINAL_NUDGE_DAYS):
        resume_days = TRIAL_DECISION_GRACE_DAYS - FINAL_NUDGE_DAYS
        out.append(
            {
                "kind": "trial_final",
                "subject": "We'll move you to the Free plan shortly",
                "body": (
                    "Still thinking it over? No action needed: in about "
                    f"{resume_days} days we'll move you to the Free plan "
                    "automatically and your Monday digest will resume. Upgrade "
                    f"any time to get the daily version back.\n\n{url}"
                ),
                "sms": (
                    f"Cirvia: no action needed, Free plan resumes in ~{resume_days} "
                    f"days. Upgrade any time: {url}"
                ),
            }
        )
    return out


async def run_trial_notices(repo: Any, settings: Any) -> dict[str, Any]:
    """Daily job body: queue due trial notices. DB-only; safe to re-run."""
    now = datetime.now(timezone.utc)
    queued = 0
    scanned = 0
    for user in await repo.list_trial_users():
        scanned += 1
        for notice in _notices_for(user, now, settings):
            try:
                if await repo.has_outbound_of_kind(user.id, notice["kind"]):
                    continue
                await repo.enqueue_outbound(
                    notice["body"],
                    user_id=user.id,
                    kind=notice["kind"],
                    subject=notice["subject"],
                    sms_body=notice["sms"],
                    # Trial notices are time-sensitive and short — exactly the
                    # shape push is good at. The kind here is the notice's own
                    # ("trial_ending" etc.), which no device subscribes to by
                    # default, so this is opt-in via /me/devices/kinds.
                    push=True,
                    push_title="Cirvia",
                    push_body=notice["sms"],
                    deep_link="cirvia://settings/plan",
                )
                queued += 1
            except Exception:  # noqa: BLE001 - one bad user never aborts the scan
                logger.warning(
                    "trial notice %s for %s failed", notice["kind"], user.id,
                    exc_info=True,
                )
    return {"scanned": scanned, "queued": queued, "at": now.isoformat()}
