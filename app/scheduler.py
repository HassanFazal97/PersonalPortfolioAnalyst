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


class DigestScheduler:
    def __init__(
        self,
        job: Callable[[], Awaitable[None]],
        *,
        cron: str,
        timezone: str,
    ) -> None:
        self._job = job
        self._scheduler = AsyncIOScheduler(timezone=timezone)
        self._trigger = CronTrigger.from_crontab(cron, timezone=timezone)

    def start(self) -> None:
        self._scheduler.add_job(self._job, self._trigger, id="morning_digest",
                                replace_existing=True)
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
        self._scheduler.add_job(
            self._job, self._trigger, id=self._job_id, replace_existing=True
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
        self._scheduler.add_job(
            self._job, self._trigger, id=self._job_id, replace_existing=True
        )
        self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    @property
    def running(self) -> bool:
        return self._scheduler.running
