"""Adapter contract for outbound delivery channels.

Each adapter wraps one provider behind ``send``; the dispatcher routes queue
rows to adapters by channel name and never knows provider details. ``permanent``
distinguishes failures worth retrying (network, 429, 5xx) from ones that never
succeed again (bad number, deleted webhook) so the queue doesn't burn attempts.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol

import httpx


@dataclass
class SendResult:
    ok: bool
    provider_message_id: str | None = None
    error: str | None = None
    permanent: bool = False


@asynccontextmanager
async def http_client(
    shared: httpx.AsyncClient | None, timeout: float
) -> AsyncIterator[httpx.AsyncClient]:
    """Yield the shared connection-pooled client when one was injected
    (build_adapters wires a process-wide client so sends reuse TCP+TLS),
    else a one-shot client — adapters constructed directly, as tests do,
    keep the old per-call behaviour. ``timeout`` applies to the one-shot
    path; the shared client carries its own."""
    if shared is not None and not shared.is_closed:
        yield shared
    else:
        async with httpx.AsyncClient(timeout=timeout) as client:
            yield client


class ChannelAdapter(Protocol):
    channel: str

    async def send(
        self, destination: str, body: str, payload: dict[str, Any]
    ) -> SendResult: ...
