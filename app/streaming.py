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
from collections import OrderedDict, deque
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
    from the persisted progress snapshot, so drops are cosmetic.

    Set ``replay_size`` to keep the last N events per key so a subscriber that
    arrives late — or comes back after the phone suspended the app — can be
    handed everything it missed. Without it, dropping events is only cosmetic
    for jobs whose progress is persisted elsewhere; for chat the dropped
    events would be the ``text_delta`` frames, i.e. the answer itself.
    """

    _QUEUE_SIZE = 256

    def __init__(self, *, replay_size: int = 0, max_histories: int = 64) -> None:
        self._subs: dict[uuid.UUID, list[asyncio.Queue]] = {}
        self._replay_size = replay_size
        self._max_histories = max_histories
        # Ordered so the oldest run's history is the one evicted at the cap.
        # Kept past close() on purpose: replaying a *finished* run is the
        # whole point — that is how a backgrounded client gets its answer.
        self._history: OrderedDict[uuid.UUID, deque[dict[str, Any]]] = OrderedDict()
        self._finished: set[uuid.UUID] = set()

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
        self._record(key, event)
        for q in self._subs.get(key, []):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def _record(self, key: uuid.UUID, event: dict[str, Any]) -> None:
        if not self._replay_size:
            return
        buffer = self._history.get(key)
        if buffer is None:
            buffer = deque(maxlen=self._replay_size)
            self._history[key] = buffer
            while len(self._history) > self._max_histories:
                evicted, _ = self._history.popitem(last=False)
                self._finished.discard(evicted)
        self._history.move_to_end(key)
        buffer.append(event)

    def open(self, key: uuid.UUID) -> None:
        """Register a run before its first event.

        Without this a subscriber arriving in the gap between "job started"
        and "first event published" would look indistinguishable from one
        asking about a run whose buffer was evicted long ago.
        """
        if not self._replay_size:
            return
        self._finished.discard(key)
        if key not in self._history:
            self._history[key] = deque(maxlen=self._replay_size)
        self._history.move_to_end(key)
        while len(self._history) > self._max_histories:
            evicted, _ = self._history.popitem(last=False)
            self._finished.discard(evicted)

    def history(self, key: uuid.UUID) -> list[dict[str, Any]]:
        """Everything published for ``key`` that is still buffered."""
        return list(self._history.get(key, ()))

    def is_finished(self, key: uuid.UUID) -> bool:
        """True once ``close`` has run — the run is over and its history, if
        any, is all a new subscriber will ever get."""
        return key in self._finished

    def is_known(self, key: uuid.UUID) -> bool:
        """True while the broker still holds live subscribers or history."""
        return key in self._subs or key in self._history

    def close(self, key: uuid.UUID) -> None:
        """Terminate all subscribers for a finished job."""
        if self._replay_size:
            self._finished.add(key)
        for q in self._subs.pop(key, []):
            try:
                q.put_nowait(SENTINEL)
            except asyncio.QueueFull:
                pass

    def forget(self, key: uuid.UUID) -> None:
        """Drop a key's buffered history outright."""
        self._history.pop(key, None)
        self._finished.discard(key)
