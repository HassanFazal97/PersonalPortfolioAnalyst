"""Server-sent-events plumbing: SSE framing, the queue-draining response
generator, and an in-process progress broker for long-running jobs.

Hand-written instead of sse-starlette: the framing is ~15 lines and we need
to own the heartbeat cadence and anti-buffering headers anyway. Single-process
pub/sub is legitimate here for the same reason the ``active_chats`` guard is —
the app runs as one process (see the note next to it in ``app.main``).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncIterator

from fastapi import Request
from fastapi.responses import StreamingResponse

# Terminates the SSE generator when pushed onto the queue.
SENTINEL: dict[str, Any] = {"type": "__sentinel__"}

# Comment frame: keeps proxies from idling the connection out and defeats
# response buffering that waits for "enough" bytes.
_PING = ": ping\n\n"
_HEARTBEAT_SECONDS = 15.0

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def sse_frame(event: dict[str, Any]) -> str:
    """One SSE frame; the dict's ``type`` becomes the event name."""
    name = event.get("type", "message")
    return f"event: {name}\ndata: {json.dumps(event, default=str)}\n\n"


def sse_response(queue: asyncio.Queue, request: Request) -> StreamingResponse:
    """Drain ``queue`` into an SSE stream until SENTINEL arrives.

    A disconnected client only stops the *sending* — whatever task feeds the
    queue keeps running and owns its own persistence/cleanup.
    """

    async def gen() -> AsyncIterator[str]:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    return
                yield _PING
                continue
            if event is SENTINEL or event.get("type") == SENTINEL["type"]:
                return
            yield sse_frame(event)
            if await request.is_disconnected():
                return

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


class ProgressBroker:
    """In-process pub/sub for job progress, keyed by an id (e.g. a deep-dive
    report id). Subscribers get their own bounded queue; a slow subscriber
    drops events rather than stalling the publisher — reconnects rehydrate
    from the persisted progress snapshot, so drops are cosmetic."""

    _QUEUE_SIZE = 256

    def __init__(self) -> None:
        self._subs: dict[uuid.UUID, list[asyncio.Queue]] = {}

    def subscribe(self, key: uuid.UUID) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._QUEUE_SIZE)
        self._subs.setdefault(key, []).append(q)
        return q

    def unsubscribe(self, key: uuid.UUID, q: asyncio.Queue) -> None:
        queues = self._subs.get(key)
        if not queues:
            return
        try:
            queues.remove(q)
        except ValueError:
            pass
        if not queues:
            self._subs.pop(key, None)

    def publish(self, key: uuid.UUID, event: dict[str, Any]) -> None:
        for q in self._subs.get(key, []):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def close(self, key: uuid.UUID) -> None:
        """Terminate all subscribers for a finished job."""
        for q in self._subs.pop(key, []):
            try:
                q.put_nowait(SENTINEL)
            except asyncio.QueueFull:
                pass
