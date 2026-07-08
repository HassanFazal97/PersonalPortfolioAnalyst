"""Dispatcher routing, backoff, and failure handling with fake adapters."""

import uuid
from types import SimpleNamespace

from app.delivery.adapters.base import SendResult
from app.delivery.dispatcher import BACKOFF_SECONDS, Dispatcher, retry_delay


class FakeQueueRepo:
    def __init__(self, messages):
        self.messages = messages
        self.results = {}

    async def claim_due_outbound(self, limit=25, *, lease_seconds=120):
        return self.messages[:limit]

    async def record_send_result(self, msg_id, **kwargs):
        self.results[msg_id] = kwargs
        if kwargs["ok"]:
            return "sent"
        if kwargs["permanent"]:
            return "failed"
        return "queued"


class FakeAdapter:
    channel = "discord"

    def __init__(self, result):
        self._result = result
        self.calls = []

    async def send(self, destination, body, payload):
        self.calls.append((destination, body, payload))
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _msg(channel="discord", attempts=0):
    return SimpleNamespace(
        id=uuid.uuid4(),
        channel=channel,
        destination="https://discord.com/api/webhooks/1/x",
        body="hello",
        payload={"kind": "digest"},
        attempts=attempts,
    )


async def test_dispatch_routes_and_records_success():
    msg = _msg()
    adapter = FakeAdapter(SendResult(ok=True, provider_message_id="abc"))
    repo = FakeQueueRepo([msg])
    n = await Dispatcher(repo, {"discord": adapter}).tick()
    assert n == 1
    assert adapter.calls[0][1] == "hello"
    recorded = repo.results[msg.id]
    assert recorded["ok"] is True
    assert recorded["provider_message_id"] == "abc"


async def test_dispatch_unconfigured_channel_fails_permanently():
    msg = _msg(channel="sms")
    repo = FakeQueueRepo([msg])
    await Dispatcher(repo, {}).tick()
    recorded = repo.results[msg.id]
    assert recorded["ok"] is False
    assert recorded["permanent"] is True


async def test_dispatch_adapter_exception_is_transient():
    msg = _msg()
    repo = FakeQueueRepo([msg])
    adapter = FakeAdapter(RuntimeError("boom"))
    await Dispatcher(repo, {"discord": adapter}).tick()
    recorded = repo.results[msg.id]
    assert recorded["ok"] is False
    assert recorded["permanent"] is False
    assert "boom" in recorded["error"]


async def test_dispatch_passes_backoff_for_attempt_count():
    msg = _msg(attempts=1)  # this will be the 2nd attempt
    repo = FakeQueueRepo([msg])
    adapter = FakeAdapter(SendResult(ok=False, error="429"))
    await Dispatcher(repo, {"discord": adapter}).tick()
    assert repo.results[msg.id]["retry_delay_seconds"] == BACKOFF_SECONDS[1]


def test_retry_delay_schedule_and_clamp():
    assert retry_delay(1) == 60
    assert retry_delay(2) == 300
    assert retry_delay(3) == 1800
    assert retry_delay(4) == 7200
    assert retry_delay(99) == 7200
