"""Scheduled-job heartbeats and /health staleness derivation (app/jobs.py),
plus the APScheduler hardening flags on the scheduler classes."""

from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.jobs import cron_state, heartbeat_wrapped, interval_state, job_health
from app.scheduler import (
    DeliveryScheduler,
    DigestScheduler,
    IntervalScheduler,
    cron_trigger_from_crontab,
)
from tests.fakes import FakeRepo


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


# ---- heartbeat_wrapped ------------------------------------------------------

async def test_wrapper_records_attempt_and_success():
    repo = FakeRepo()
    ran = []

    async def job():
        ran.append(1)

    await heartbeat_wrapped("morning_digest", repo, job)()

    assert ran == [1]
    hb = repo.job_heartbeats["morning_digest"]
    assert hb.last_attempt_at is not None
    assert hb.last_success_at is not None
    assert hb.consecutive_failures == 0


async def test_wrapper_records_failure_and_reraises():
    repo = FakeRepo()

    async def job():
        raise RuntimeError("digest exploded")

    wrapped = heartbeat_wrapped("morning_digest", repo, job)
    with pytest.raises(RuntimeError):
        await wrapped()
    with pytest.raises(RuntimeError):
        await wrapped()

    hb = repo.job_heartbeats["morning_digest"]
    assert hb.last_success_at is None
    assert hb.consecutive_failures == 2
    assert "digest exploded" in hb.last_error


async def test_wrapper_is_best_effort_job_runs_despite_heartbeat_failure():
    # The instrumentation must never become a single point of failure for
    # delivery: a broken heartbeat write still runs the job.
    repo = FakeRepo()
    ran = []

    async def broken_writer(*a, **kw):
        raise ConnectionError("db blip")

    repo.record_job_attempt = broken_writer
    repo.record_job_result = broken_writer

    async def job():
        ran.append(1)

    await heartbeat_wrapped("delivery_dispatch", repo, job)()
    assert ran == [1]


async def test_wrapper_success_resets_failure_count():
    repo = FakeRepo()
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("once")

    wrapped = heartbeat_wrapped("macro_scan", repo, flaky)
    with pytest.raises(RuntimeError):
        await wrapped()
    await wrapped()

    hb = repo.job_heartbeats["macro_scan"]
    assert hb.consecutive_failures == 0
    assert hb.last_error is None
    assert hb.last_success_at is not None


# ---- interval_state ---------------------------------------------------------

def test_interval_state_thresholds():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    interval = 30.0
    assert interval_state(None, now, interval) == "unknown"
    assert interval_state(now - timedelta(seconds=45), now, interval) == "live"
    assert interval_state(now - timedelta(seconds=120), now, interval) == "degraded"
    assert interval_state(now - timedelta(seconds=400), now, interval) == "offline"


# ---- cron_state (digest cron "45 7 * * 1-5", America/Toronto) ---------------

CRON = "45 7 * * 1-5"
TZ = "America/Toronto"


def _toronto(y, m, d, hh, mm):
    from zoneinfo import ZoneInfo

    return datetime(y, m, d, hh, mm, tzinfo=ZoneInfo(TZ))


def test_cron_state_weekend_gap_is_live():
    # Friday 2026-07-10 success; Saturday afternoon has no missed fires.
    last = _toronto(2026, 7, 10, 7, 46)
    now = _toronto(2026, 7, 11, 15, 0)
    assert cron_state(last, now, CRON, TZ) == "live"


def test_cron_state_one_missed_fire_is_degraded():
    # Friday success; Monday 10:00 — Monday 07:45 fired >1h ago and was missed.
    last = _toronto(2026, 7, 10, 7, 46)
    now = _toronto(2026, 7, 13, 10, 0)
    assert cron_state(last, now, CRON, TZ) == "degraded"


def test_cron_state_within_grace_is_still_live():
    # Monday 08:00, 15 minutes after the fire: inside the 1h grace window.
    last = _toronto(2026, 7, 10, 7, 46)
    now = _toronto(2026, 7, 13, 8, 0)
    assert cron_state(last, now, CRON, TZ) == "live"


def test_cron_state_two_missed_fires_is_offline():
    # Friday success; Tuesday noon — Monday and Tuesday both missed.
    last = _toronto(2026, 7, 10, 7, 46)
    now = _toronto(2026, 7, 14, 12, 0)
    assert cron_state(last, now, CRON, TZ) == "offline"


def test_cron_state_never_succeeded_is_unknown():
    assert cron_state(None, _toronto(2026, 7, 13, 12, 0), CRON, TZ) == "unknown"


def test_cron_state_bad_cron_is_unknown():
    last = _toronto(2026, 7, 10, 7, 46)
    assert cron_state(last, _toronto(2026, 7, 13, 12, 0), "not a cron", TZ) == "unknown"


# ---- job_health -------------------------------------------------------------

async def test_job_health_disabled_jobs_and_unknown():
    settings = _settings()  # macro interval 0, anomaly cron "" -> disabled
    health = job_health({}, settings)
    assert health["macro_scan"] == {"state": "disabled"}
    assert health["anomaly_scan"] == {"state": "disabled"}
    assert health["morning_digest"]["state"] == "unknown"
    assert health["delivery_dispatch"]["state"] == "unknown"
    # fundamentals_refresh has a default cron -> enabled, never run -> unknown.
    assert health["fundamentals_refresh"]["state"] == "unknown"
    disabled = job_health({}, _settings(FUNDAMENTALS_REFRESH_CRON=""))
    assert disabled["fundamentals_refresh"] == {"state": "disabled"}
    # news_refresh mirrors that: default cron -> enabled, "" -> disabled.
    assert health["news_refresh"]["state"] == "unknown"
    news_off = job_health({}, _settings(NEWS_REFRESH_CRON=""))
    assert news_off["news_refresh"] == {"state": "disabled"}


async def test_job_health_news_refresh_live_after_success():
    repo = FakeRepo()
    await repo.record_job_result("news_refresh", ok=True)
    health = job_health(repo.job_heartbeats, _settings())
    assert health["news_refresh"]["state"] == "live"


async def test_job_health_fundamentals_refresh_live_after_success():
    repo = FakeRepo()
    await repo.record_job_result("fundamentals_refresh", ok=True)
    health = job_health(repo.job_heartbeats, _settings())
    assert health["fundamentals_refresh"]["state"] == "live"


async def test_job_health_live_after_success():
    repo = FakeRepo()
    await repo.record_job_result("delivery_dispatch", ok=True)
    await repo.record_job_result("morning_digest", ok=True)
    health = job_health(repo.job_heartbeats, _settings())
    assert health["delivery_dispatch"]["state"] == "live"
    assert health["morning_digest"]["state"] == "live"
    assert health["morning_digest"]["last_error"] is None


async def test_job_health_repeated_failures_force_degraded():
    repo = FakeRepo()
    await repo.record_job_result("delivery_dispatch", ok=True)
    for _ in range(3):
        await repo.record_job_result("delivery_dispatch", ok=False, error="boom")
    # last_success is seconds old (inside the live window), but 3 consecutive
    # failures must still surface.
    health = job_health(repo.job_heartbeats, _settings())
    assert health["delivery_dispatch"]["state"] == "degraded"
    assert health["delivery_dispatch"]["consecutive_failures"] == 3
    assert health["delivery_dispatch"]["last_error"] == "boom"


# ---- crontab day-of-week translation -----------------------------------------
# APScheduler's from_crontab numbers weekdays 0=Monday while standard cron uses
# 0=Sunday: the stock digest cron "45 7 * * 1-5" silently fired Tue–Sat, so the
# Monday digest (the ONLY one Free users get) never ran. These pin the fix.

def _fires_on(cron: str) -> set[str]:
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    trigger = cron_trigger_from_crontab(cron, timezone=TZ)
    prev = datetime(2026, 7, 12, 0, 0, tzinfo=ZoneInfo(TZ))  # a Sunday
    days = set()
    for _ in range(7):
        nxt = trigger.get_next_fire_time(None, prev)
        days.add(nxt.strftime("%a"))
        prev = nxt + timedelta(minutes=1)
    return days


def test_crontab_dow_1_to_5_means_monday_to_friday():
    assert _fires_on("45 7 * * 1-5") == {"Mon", "Tue", "Wed", "Thu", "Fri"}


def test_crontab_dow_0_means_sunday():
    assert _fires_on("45 7 * * 0") == {"Sun"}
    assert _fires_on("45 7 * * 7") == {"Sun"}


def test_crontab_dow_names_and_star_pass_through():
    assert _fires_on("45 7 * * mon-fri") == {"Mon", "Tue", "Wed", "Thu", "Fri"}
    assert _fires_on("45 7 * * *") == {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}


def test_crontab_dow_list_and_step():
    assert _fires_on("45 7 * * 1,3,5") == {"Mon", "Wed", "Fri"}
    # */2 over cron Sun..Sat = Sun, Tue, Thu, Sat
    assert _fires_on("45 7 * * */2") == {"Sun", "Tue", "Thu", "Sat"}


# ---- scheduler hardening flags -----------------------------------------------

async def _noop():
    pass


def _job_kwargs(monkeypatch, scheduler_obj):
    captured = {}

    def fake_add_job(self, func, trigger, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(type(scheduler_obj._scheduler), "add_job", fake_add_job)
    monkeypatch.setattr(type(scheduler_obj._scheduler), "start", lambda self: None)
    scheduler_obj.start()
    return captured


def test_digest_scheduler_misfire_flags(monkeypatch):
    s = DigestScheduler(_noop, cron="45 7 * * 1-5", timezone="America/Toronto")
    kwargs = _job_kwargs(monkeypatch, s)
    # APScheduler's default grace is 1 SECOND — a busy loop at 07:45 would
    # silently skip the day's digest without this.
    assert kwargs["misfire_grace_time"] == 3600
    assert kwargs["coalesce"] is True
    assert kwargs["max_instances"] == 1
    assert kwargs["id"] == "morning_digest"


def test_delivery_scheduler_misfire_flags(monkeypatch):
    s = DeliveryScheduler(_noop, seconds=30, timezone="America/Toronto")
    kwargs = _job_kwargs(monkeypatch, s)
    assert kwargs["misfire_grace_time"] == 30
    assert kwargs["coalesce"] is True
    assert kwargs["max_instances"] == 1
    assert kwargs["id"] == "delivery_dispatch"


def test_interval_scheduler_misfire_flags(monkeypatch):
    s = IntervalScheduler(_noop, minutes=60, timezone="America/Toronto")
    kwargs = _job_kwargs(monkeypatch, s)
    assert kwargs["misfire_grace_time"] == 300
    assert kwargs["coalesce"] is True
    assert kwargs["max_instances"] == 1
    assert kwargs["id"] == "macro_scan"
