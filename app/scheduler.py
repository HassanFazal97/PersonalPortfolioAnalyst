"""Scheduling behind a small stub interface so Trigger.dev can replace it later.

``DigestScheduler`` wraps APScheduler's AsyncIOScheduler with a single cron job.
Nothing outside this module imports APScheduler, so swapping the backend means
implementing the same ``start``/``shutdown``/``running`` surface.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger


def _translate_crontab_dow(field: str) -> str:
    """Convert a crontab day-of-week field to APScheduler numbering.

    Standard cron counts 0/7=Sunday, 1=Monday … 6=Saturday, but APScheduler's
    ``from_crontab`` feeds the field to its own CronTrigger where 0=Monday —
    so ``1-5`` (cron Mon–Fri) silently becomes Tue–Sat and the Monday digest
    never fires. Numeric tokens are expanded and remapped; names ("mon-fri")
    and ``*`` already mean the same thing in both conventions."""
    if field == "*" or any(c.isalpha() for c in field):
        return field
    days: set[int] = set()
    for token in field.split(","):
        step = 1
        if "/" in token:
            token, step_s = token.split("/", 1)
            step = int(step_s)
        if token == "*":
            values = list(range(0, 7))
        elif "-" in token:
            lo, hi = token.split("-", 1)
            values = list(range(int(lo), int(hi) + 1))
        else:
            values = [int(token)]
        days.update(v for i, v in enumerate(values) if i % step == 0)
    # cron 0/7=Sun → APScheduler 6; cron 1=Mon → 0; … cron 6=Sat → 5.
    return ",".join(str((d - 1) % 7) for d in sorted({d % 7 for d in days}))


def cron_trigger_from_crontab(cron: str, *, timezone: str) -> CronTrigger:
    """``CronTrigger.from_crontab`` with STANDARD cron day-of-week semantics."""
    fields = cron.split()
    if len(fields) == 5:
        fields[4] = _translate_crontab_dow(fields[4])
        cron = " ".join(fields)
    return CronTrigger.from_crontab(cron, timezone=timezone)


class DigestScheduler:
    def __init__(
        self,
        job: Callable[[], Awaitable[None]],
        *,
        cron: str,
        timezone: str,
        job_id: str = "morning_digest",
        misfire_grace_seconds: int = 3600,
    ) -> None:
        self._job = job
        self._job_id = job_id
        self._misfire_grace_seconds = misfire_grace_seconds
        self._scheduler = AsyncIOScheduler(timezone=timezone)
        self._trigger = cron_trigger_from_crontab(cron, timezone=timezone)

    def start(self) -> None:
        # APScheduler's default misfire_grace_time is 1 SECOND: a busy event
        # loop at fire time silently skips the day's run. Up to an hour late,
        # the morning digest is still worth sending.
        self._scheduler.add_job(
            self._job,
            self._trigger,
            id=self._job_id,
            replace_existing=True,
            misfire_grace_time=self._misfire_grace_seconds,
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    @property
    def running(self) -> bool:
        return self._scheduler.running


class DeliveryScheduler:
    """Runs ``job`` every ``seconds``. Used to drain the outbound delivery
    queue; same swappable surface as ``DigestScheduler``."""

    def __init__(
        self,
        job: Callable[[], Awaitable[object]],
        *,
        seconds: int,
        timezone: str,
        job_id: str = "delivery_dispatch",
    ) -> None:
        self._job = job
        self._job_id = job_id
        self._scheduler = AsyncIOScheduler(timezone=timezone)
        self._trigger = IntervalTrigger(seconds=seconds, timezone=timezone)

    def start(self) -> None:
        # max_instances=1 prevents overlapping queue drains if a tick runs
        # long; a missed 30s tick is stale within one interval, so coalesce.
        self._scheduler.add_job(
            self._job,
            self._trigger,
            id=self._job_id,
            replace_existing=True,
            misfire_grace_time=30,
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    @property
    def running(self) -> bool:
        return self._scheduler.running


class IntervalScheduler:
    """Runs ``job`` every ``minutes``. Used for the macro scan; same swappable
    surface as ``DigestScheduler`` so the backend can be replaced later."""

    def __init__(
        self,
        job: Callable[[], Awaitable[None]],
        *,
        minutes: int,
        timezone: str,
        job_id: str = "macro_scan",
    ) -> None:
        self._job = job
        self._job_id = job_id
        self._scheduler = AsyncIOScheduler(timezone=timezone)
        self._trigger = IntervalTrigger(minutes=minutes, timezone=timezone)

    def start(self) -> None:
        # Macro scans cost real dollars: never let missed fires pile up and
        # replay (coalesce), never run two scans concurrently.
        self._scheduler.add_job(
            self._job,
            self._trigger,
            id=self._job_id,
            replace_existing=True,
            misfire_grace_time=300,
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    @property
    def running(self) -> bool:
        return self._scheduler.running
