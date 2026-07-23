"""Streaming seam: run_agent(on_event=...), the SSE writer, and the broker."""

import asyncio
import json
import uuid

import app.tools.market as market
from app.agent.budget import Budget
from app.agent.loop import run_agent
from app.agent.prompts import CHAT_SYSTEM_PROMPT
from app.streaming import SENTINEL, ProgressBroker, sse_frame
from app.tools.registry import CHAT_TOOLS
from tests.fakes import (
    FakeRepo,
    ScriptedAnthropic,
    ScriptedStreamingAnthropic,
    text_turn,
    tool_use_turn,
)


def _quote_stub(monkeypatch):
    market.cache_clear()
    monkeypatch.setattr(
        market,
        "_fetch_quote_raw",
        lambda t: {"last_price": 200.0, "previous_close": 190.0, "volume": 5},
    )


def _script():
    return [
        tool_use_turn("t1", "get_quote", {"tickers": ["NVDA"]}),
        text_turn("NVDA is at 200."),
    ]


async def test_on_event_with_nonstreaming_client_emits_tool_steps(monkeypatch):
    """A client without .stream stays on messages.create but still emits
    run/iteration/tool events — protects the digest pipeline's call path."""
    _quote_stub(monkeypatch)
    events: list[dict] = []

    async def on_event(ev):
        events.append(ev)

    client = ScriptedAnthropic(_script())
    result = await run_agent(
        "What's NVDA doing?",
        trigger="chat",
        system_prompt=CHAT_SYSTEM_PROMPT,
        tools=CHAT_TOOLS,
        budget=Budget(max_iterations=10, max_cost_usd=0.50, model="claude-sonnet-4-6"),
        db=FakeRepo(),
        client=client,
        on_event=on_event,
    )

    assert result.status == "completed"
    types = [e["type"] for e in events]
    assert types.count("run_start") == 1
    assert types.count("iteration") == 2
    assert "text_delta" not in types  # no .stream on this client
    start = next(e for e in events if e["type"] == "tool_start")
    assert start["name"] == "get_quote"
    assert start["label"] == "Fetching live quotes"
    assert start["input_summary"] == "NVDA"
    end = next(e for e in events if e["type"] == "tool_end")
    assert end["ok"] is True


async def test_streaming_client_forwards_text_deltas(monkeypatch):
    """With a streaming-capable client, text deltas arrive and the final
    result + persisted rows match the non-streaming path exactly."""
    _quote_stub(monkeypatch)
    events: list[dict] = []

    async def on_event(ev):
        events.append(ev)

    repo = FakeRepo()
    result = await run_agent(
        "What's NVDA doing?",
        trigger="chat",
        system_prompt=CHAT_SYSTEM_PROMPT,
        tools=CHAT_TOOLS,
        budget=Budget(max_iterations=10, max_cost_usd=0.50, model="claude-sonnet-4-6"),
        db=repo,
        client=ScriptedStreamingAnthropic(_script()),
        on_event=on_event,
    )

    assert result.status == "completed"
    assert result.answer == "NVDA is at 200."
    streamed = "".join(e["text"] for e in events if e["type"] == "text_delta")
    assert streamed == "NVDA is at 200."
    # Observer parity with the non-streaming path
    assert len(repo.model_calls) == 2
    assert len(repo.tool_calls) == 1
    run = next(iter(repo.runs.values()))
    assert run["status"] == "completed"


async def test_dead_event_callback_never_aborts_run(monkeypatch):
    _quote_stub(monkeypatch)

    async def broken(ev):
        raise RuntimeError("consumer went away")

    result = await run_agent(
        "What's NVDA doing?",
        trigger="chat",
        system_prompt=CHAT_SYSTEM_PROMPT,
        tools=CHAT_TOOLS,
        budget=Budget(max_iterations=10, max_cost_usd=0.50, model="claude-sonnet-4-6"),
        db=FakeRepo(),
        client=ScriptedAnthropic(_script()),
        on_event=broken,
    )
    assert result.status == "completed"
    assert result.answer == "NVDA is at 200."


async def test_budget_summary_streams_and_emits_status(monkeypatch):
    _quote_stub(monkeypatch)
    events: list[dict] = []

    async def on_event(ev):
        events.append(ev)

    client = ScriptedStreamingAnthropic(
        [
            tool_use_turn("t1", "get_quote", {"tickers": ["NVDA"]}, in_tok=1_000_000, out_tok=0),
            text_turn("Summary: NVDA at 200."),
        ]
    )
    result = await run_agent(
        "loop forever",
        trigger="chat",
        system_prompt=CHAT_SYSTEM_PROMPT,
        tools=CHAT_TOOLS,
        budget=Budget(max_iterations=10, max_cost_usd=0.10, model="claude-sonnet-4-6"),
        db=FakeRepo(),
        client=client,
        on_event=on_event,
    )
    assert result.status == "budget_exceeded"
    assert result.answer == "Summary: NVDA at 200."
    assert any(e["type"] == "status" and e["status"] == "budget_summary" for e in events)
    # The forced summary turn streams too
    assert "".join(e["text"] for e in events if e["type"] == "text_delta").endswith(
        "Summary: NVDA at 200."
    )


def test_sse_frame_format():
    frame = sse_frame({"type": "tool_start", "name": "get_quote"})
    assert frame.startswith("event: tool_start\n")
    assert frame.endswith("\n\n")
    payload = json.loads(frame.split("data: ", 1)[1].strip())
    assert payload["name"] == "get_quote"


async def test_progress_broker_pubsub_and_close():
    broker = ProgressBroker()
    key = uuid.uuid4()
    q = broker.subscribe(key)
    broker.publish(key, {"type": "dd_stage", "stage": "plan"})
    assert (await q.get())["stage"] == "plan"
    broker.close(key)
    assert (await q.get()) is SENTINEL
    # Publishing after close is a no-op, not an error
    broker.publish(key, {"type": "dd_stage", "stage": "research"})


async def test_progress_broker_slow_subscriber_drops_not_blocks():
    broker = ProgressBroker()
    key = uuid.uuid4()
    q = broker.subscribe(key)
    for i in range(ProgressBroker._QUEUE_SIZE + 10):
        broker.publish(key, {"type": "tick", "n": i})  # must never raise/block
    assert q.qsize() == ProgressBroker._QUEUE_SIZE
    broker.unsubscribe(key, q)
    assert asyncio.iscoroutinefunction(q.get)  # still a normal queue
