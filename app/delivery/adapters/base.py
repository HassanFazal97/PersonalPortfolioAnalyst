"""Adapter contract for outbound delivery channels.

Each adapter wraps one provider behind ``send``; the dispatcher routes queue
rows to adapters by channel name and never knows provider details. ``permanent``
distinguishes failures worth retrying (network, 429, 5xx) from ones that never
succeed again (bad number, deleted webhook) so the queue doesn't burn attempts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class SendResult:
    ok: bool
    provider_message_id: str | None = None
    error: str | None = None
    permanent: bool = False


class ChannelAdapter(Protocol):
    channel: str

    async def send(
        self, destination: str, body: str, payload: dict[str, Any]
    ) -> SendResult: ...
