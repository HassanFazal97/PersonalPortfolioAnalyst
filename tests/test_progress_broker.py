"""ProgressBroker: fan-out, and the bounded replay buffer chat depends on."""

import asyncio
import uuid

import pytest

from app.streaming import SENTINEL, ProgressBroker


def test_publish_fans_out_to_every_subscriber():
    broker = ProgressBroker()
    key = uuid.uuid4()
    a, b = broker.subscribe(key), broker.subscribe(key)

    broker.publish(key, {"type": "tick"})

    assert a.get_nowait() == {"type": "tick"}
    assert b.get_nowait() == {"type": "tick"}


def test_close_sends_the_sentinel_and_drops_subscribers():
    broker = ProgressBroker()
    key = uuid.uuid4()
    q = broker.subscribe(key)

    broker.close(key)

    assert q.get_nowait() is SENTINEL
    # A later publish reaches nobody rather than raising.
    broker.publish(key, {"type": "late"})
    with pytest.raises(asyncio.QueueEmpty):
        q.get_nowait()


def test_a_full_queue_drops_events_instead_of_stalling():
    """The publisher must never block on a slow subscriber."""
    broker = ProgressBroker()
    key = uuid.uuid4()
    q = broker.subscribe(key)
    for i in range(ProgressBroker._QUEUE_SIZE + 10):
        broker.publish(key, {"type": "tick", "i": i})
    assert q.qsize() == ProgressBroker._QUEUE_SIZE


def test_no_replay_buffer_by_default():
    """Deep dive rehydrates from its persisted progress, so it keeps the
    zero-memory behaviour it has always had."""
    broker = ProgressBroker()
    key = uuid.uuid4()
    broker.publish(key, {"type": "tick"})
    assert broker.history(key) == []
    assert not broker.is_known(key)


def test_replay_buffer_records_even_with_no_subscribers():
    """The whole point: the run finishes while the phone is asleep."""
    broker = ProgressBroker(replay_size=10)
    key = uuid.uuid4()

    broker.open(key)
    broker.publish(key, {"type": "run_start"})
    broker.publish(key, {"type": "text_delta", "text": "hi"})
    broker.publish(key, {"type": "done", "answer": "hi"})
    broker.close(key)

    assert [e["type"] for e in broker.history(key)] == [
        "run_start",
        "text_delta",
        "done",
    ]
    assert broker.is_finished(key)
    assert broker.is_known(key)


def test_replay_buffer_is_bounded_and_keeps_the_newest():
    """A long run must not grow without limit — and the tail matters most,
    since `done` carries the answer."""
    broker = ProgressBroker(replay_size=5)
    key = uuid.uuid4()
    broker.open(key)
    for i in range(20):
        broker.publish(key, {"type": "text_delta", "i": i})
    broker.publish(key, {"type": "done"})

    history = broker.history(key)
    assert len(history) == 5
    assert history[-1]["type"] == "done"
    assert history[0]["i"] == 16


def test_open_marks_a_run_live_before_its_first_event():
    """Closes the race between /chat/start returning and the client opening
    the SSE: without this the handler cannot tell "just started" from
    "so old its buffer was evicted"."""
    broker = ProgressBroker(replay_size=10)
    key = uuid.uuid4()

    assert not broker.is_known(key)
    broker.open(key)
    assert broker.is_known(key)
    assert not broker.is_finished(key)
    assert broker.history(key) == []


def test_histories_are_capped_evicting_the_oldest_run():
    broker = ProgressBroker(replay_size=4, max_histories=3)
    keys = [uuid.uuid4() for _ in range(4)]
    for key in keys:
        broker.open(key)
        broker.publish(key, {"type": "run_start"})
        broker.close(key)

    assert not broker.is_known(keys[0])
    assert not broker.is_finished(keys[0])
    assert all(broker.is_known(k) for k in keys[1:])


def test_publishing_to_an_older_run_keeps_it_from_being_evicted():
    """Recency is by use, not creation: an in-flight run must not be evicted
    by newer ones that started after it."""
    broker = ProgressBroker(replay_size=4, max_histories=2)
    old, new = uuid.uuid4(), uuid.uuid4()

    broker.open(old)
    broker.open(new)
    broker.publish(old, {"type": "text_delta"})  # old is the most recent user

    broker.open(uuid.uuid4())  # forces an eviction

    assert broker.is_known(old)
    assert not broker.is_known(new)


def test_forget_drops_a_history():
    broker = ProgressBroker(replay_size=4)
    key = uuid.uuid4()
    broker.open(key)
    broker.publish(key, {"type": "run_start"})
    broker.close(key)

    broker.forget(key)

    assert not broker.is_known(key)
    assert not broker.is_finished(key)
    assert broker.history(key) == []
