"""Outbound delivery dispatcher: drains the queue and routes rows to adapters.

Runs in-process on a short interval (DeliveryScheduler). Each tick claims due
queued rows (leased, SKIP LOCKED — safe if a second instance ever runs) and
sends them through the adapter for their channel. Failures either requeue with
backoff or fail permanently; the repo records the outcome either way.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from app.delivery.adapters.base import ChannelAdapter, SendResult

logger = logging.getLogger(__name__)

# Transient-failure backoff by attempt number: 1m, 5m, 30m, then 2h.
BACKOFF_SECONDS = (60, 300, 1800, 7200)


def retry_delay(attempts: int) -> int:
    """Backoff for a message that has now failed ``attempts`` times."""
    return BACKOFF_SECONDS[min(max(attempts, 1) - 1, len(BACKOFF_SECONDS) - 1)]


class Dispatcher:
    def __init__(
        self,
        repo: Any,
        adapters: dict[str, ChannelAdapter],
        *,
        batch_size: int = 25,
        max_attempts: int = 5,
        unsubscribe_url_for: Callable[[uuid.UUID, str], str | None] | None = None,
    ) -> None:
        self._repo = repo
        self._adapters = adapters
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        # (user_id, channel) -> signed unsubscribe link; emails must carry one
        # (CASL), so the dispatcher stamps it into the payload at send time.
        self._unsubscribe_url_for = unsubscribe_url_for

    def _payload_for(self, msg: Any) -> dict[str, Any]:
        payload = dict(msg.payload or {})
        user_id = getattr(msg, "user_id", None)
        if (
            msg.channel == "email"
            and self._unsubscribe_url_for is not None
            and user_id is not None
        ):
            url = self._unsubscribe_url_for(user_id, msg.channel)
            if url:
                payload["unsubscribe_url"] = url
        return payload

    async def tick(self) -> int:
        """Process one batch of due messages. Returns how many were attempted."""
        messages = await self._repo.claim_due_outbound(self._batch_size)
        for msg in messages:
            adapter = self._adapters.get(msg.channel or "")
            if adapter is None:
                await self._repo.record_send_result(
                    msg.id,
                    ok=False,
                    error=f"channel '{msg.channel}' is not configured",
                    permanent=True,
                )
                continue
            try:
                result = await adapter.send(
                    msg.destination or "", msg.body, self._payload_for(msg)
                )
            except Exception as exc:  # noqa: BLE001 - adapter bugs must not kill the loop
                logger.exception("adapter %s crashed for message %s", msg.channel, msg.id)
                result = SendResult(ok=False, error=f"{type(exc).__name__}: {exc}")
            status = await self._repo.record_send_result(
                msg.id,
                ok=result.ok,
                provider_message_id=result.provider_message_id,
                error=result.error,
                permanent=result.permanent,
                max_attempts=self._max_attempts,
                retry_delay_seconds=retry_delay((msg.attempts or 0) + 1),
            )
            if not result.ok:
                logger.warning(
                    "delivery %s via %s -> %s: %s",
                    msg.id,
                    msg.channel,
                    status,
                    result.error,
                )
        return len(messages)
