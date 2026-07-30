"""Trial lifecycle notices: which notice fires when, and once each at most."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.plans import TRIAL_DECISION_GRACE_DAYS
from app.trial_notices import _notices_for, run_trial_notices
from tests.fakes import FakeRepo

pytestmark = pytest.mark.asyncio

_SETTINGS = SimpleNamespace(public_base_url="https://cirvia.ca")
_NOW = datetime.now(timezone.utc)


def _user(ends_delta_days: float, plan: str = "free"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        plan=plan,
        trial_ends_at=_NOW + timedelta(days=ends_delta_days),
    )


def _kinds(user) -> list[str]:
    return [n["kind"] for n in _notices_for(user, _NOW, _SETTINGS)]


def test_notice_selection_by_trial_phase():
    assert _kinds(_user(5)) == []                       # mid-trial: quiet
    assert _kinds(_user(1.5)) == ["trial_ending"]       # T-2 heads-up
    assert _kinds(_user(-0.5)) == ["trial_ended"]       # lapsed, undecided
    # +3 days undecided: day-of (if somehow unsent) plus the final nudge.
    assert _kinds(_user(-3.5)) == ["trial_ended", "trial_final"]
    # Past the grace window the account is plain Free — a months-late "your
    # trial just ended" reads as a bug, so long-lapsed users get nothing.
    assert _kinds(_user(-(TRIAL_DECISION_GRACE_DAYS + 1))) == []


def test_ending_soon_copy_counts_days():
    notice = _notices_for(_user(1.5), _NOW, _SETTINGS)[0]
    assert "2 days" in notice["subject"]
    assert "https://cirvia.ca/app/settings?billing=upgrade" in notice["body"]


async def test_run_queues_each_notice_once():
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, trial_ends_at=_NOW - timedelta(hours=6))

    first = await run_trial_notices(repo, _SETTINGS)
    assert first["queued"] == 1
    assert await repo.has_outbound_of_kind(uid, "trial_ended")
    # Re-running the daily scan never re-sends.
    second = await run_trial_notices(repo, _SETTINGS)
    assert second["queued"] == 0


async def test_run_skips_paying_and_untrialed_users():
    repo = FakeRepo()
    repo.seed_user(uuid.uuid4(), plan="pro", trial_ends_at=_NOW - timedelta(days=1))
    repo.seed_user(uuid.uuid4())  # no trial state at all
    result = await run_trial_notices(repo, _SETTINGS)
    assert result["queued"] == 0
