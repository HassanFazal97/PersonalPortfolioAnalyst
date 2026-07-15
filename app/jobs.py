"""Scheduled-job heartbeats and health derivation.

``heartbeat_wrapped`` records attempt/success/failure around each scheduled
job into the ``job_heartbeats`` table; ``job_health`` derives a per-job
live/degraded/offline state from staleness at /health read time (state
machine adapted from Shizen's HeartbeatMonitor — pull-based here, so no
background check loop is needed).

Heartbeat writes are best-effort by design: a DB blip in the instrumentation
must never prevent the job itself from running, or health tracking becomes a
new single point of failure for delivery.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Literal

from app.config import Settings
from app.scheduler import cron_trigger_from_crontab

logger = logging.getLogger(__name__)

JobState = Literal["live", "degraded", "offline", "disabled", "unknown"]

# A job with this many consecutive failures is at least degraded even if a
# stale success timestamp is still inside the liveness window.
_FAILURES_FORCE_DEGRADED = 3


def heartbeat_wrapped(
    job_name: str, repo: Any, fn: Callable[[], Awaitable[Any]]
) -> Callable[[], Awaitable[None]]:
    """Wrap a job callable so each run records attempt + success/failure.

    Job exceptions re-raise (APScheduler's own error logging still fires);
    heartbeat write failures are logged and swallowed."""

    async def wrapped() -> None:
        try:
            await repo.record_job_attempt(job_name)
        except Exception:
            logger.warning("heartbeat attempt write failed for %s", job_name, exc_info=True)
        try:
            await fn()
        except Exception as exc:
            try:
                await repo.record_job_result(job_name, ok=False, error=repr(exc)[:500])
            except Exception:
                logger.warning("heartbeat failure write failed for %s", job_name, exc_info=True)
            raise
        try:
            await repo.record_job_result(job_name, ok=True)
        except Exception:
            logger.warning("heartbeat success write failed for %s", job_name, exc_info=True)

    return wrapped


def interval_state(
    last_success: datetime | None,
    now: datetime,
    interval_s: float,
    *,
    degraded_factor: float = 3.0,
    offline_factor: float = 10.0,
) -> JobState:
    """Staleness state for an interval job: fine until a few intervals have
    been missed (mirrors Shizen's 'one missed beat is still LIVE' ratios)."""
    if last_success is None:
        return "unknown"
    age_s = (now - last_success).total_seconds()
    if age_s > interval_s * offline_factor:
        return "offline"
    if age_s > interval_s * degraded_factor:
        return "degraded"
    return "live"


def cron_state(
    last_success: datetime | None,
    now: datetime,
    cron: str,
    tz: str,
    *,
    grace_s: float = 3600.0,
) -> JobState:
    """Staleness state for a cron job, by counting MISSED SCHEDULED FIRES
    since the last success rather than wall-clock hours — a fixed-hour
    threshold would false-alarm every weekend for the weekday digest.

    0 missed fires → live, 1 → degraded, ≥2 → offline. A fire only counts as
    missed once it is ``grace_s`` old (the job may legitimately still be
    running or slightly late)."""
    if last_success is None:
        return "unknown"
    try:
        trigger = cron_trigger_from_crontab(cron, timezone=tz)
    except ValueError:
        return "unknown"
    deadline = now - timedelta(seconds=grace_s)
    missed = 0
    prev = last_success
    while missed < 2:
        # get_next_fire_time is inclusive of the passed time — nudge past the
        # counted fire or the same one is returned forever.
        next_fire = trigger.get_next_fire_time(None, prev)
        if next_fire is None or next_fire > deadline:
            break
        missed += 1
        prev = next_fire + timedelta(seconds=1)
    if missed >= 2:
        return "offline"
    if missed == 1:
        return "degraded"
    return "live"


def job_health(
    heartbeats: dict[str, Any], settings: Settings, now: datetime | None = None
) -> dict[str, dict[str, Any]]:
    """Per-job health for GET /health. Disabled jobs report 'disabled' and
    never look stale; repeated failures force at least 'degraded'."""
    now = now or datetime.now(timezone.utc)

    specs: dict[str, dict[str, Any]] = {
        "morning_digest": {"kind": "cron", "cron": settings.digest_cron, "enabled": True},
        "macro_scan": {
            "kind": "interval",
            "interval_s": settings.macro_scan_interval_minutes * 60,
            "enabled": settings.macro_scan_interval_minutes > 0,
        },
        "anomaly_scan": {
            "kind": "cron",
            "cron": settings.anomaly_scan_cron,
            "enabled": bool(settings.anomaly_scan_cron),
        },
        "delivery_dispatch": {
            "kind": "interval",
            "interval_s": settings.delivery_interval_seconds,
            "enabled": settings.delivery_interval_seconds > 0,
        },
    }

    out: dict[str, dict[str, Any]] = {}
    for name, spec in specs.items():
        if not spec["enabled"]:
            out[name] = {"state": "disabled"}
            continue
        hb = heartbeats.get(name)
        last_success = getattr(hb, "last_success_at", None) if hb else None
        if spec["kind"] == "cron":
            state: JobState = cron_state(
                last_success, now, spec["cron"], settings.tz,
                grace_s=settings.digest_misfire_grace_seconds,
            )
        else:
            state = interval_state(
                last_success, now, spec["interval_s"],
                degraded_factor=settings.job_degraded_factor,
                offline_factor=settings.job_offline_factor,
            )
        failures = int(getattr(hb, "consecutive_failures", 0) or 0) if hb else 0
        if state == "live" and failures >= _FAILURES_FORCE_DEGRADED:
            state = "degraded"
        out[name] = {
            "state": state,
            "last_success_at": last_success.isoformat() if last_success else None,
            "last_attempt_at": (
                hb.last_attempt_at.isoformat()
                if hb is not None and getattr(hb, "last_attempt_at", None)
                else None
            ),
            "last_error": getattr(hb, "last_error", None) if hb else None,
            "consecutive_failures": failures,
        }
    return out
