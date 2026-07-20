"""Chat context injection, multi-turn memory, and the caching request shape."""

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import app.main as main
import app.tools.market as market
from app.agent.budget import Budget
from app.agent.chat_context import build_chat_context, compose_chat_system_prompt
from app.agent.loop import build_initial_messages, run_agent
from app.agent.prompts import CHAT_SYSTEM_PROMPT
from app.config import get_settings
from app.tools.registry import CHAT_TOOLS, ToolContext
from tests.fakes import FakeRepo, ScriptedAnthropic, text_turn


def _position(ticker="NVDA", currency="USD"):
    return SimpleNamespace(
        ticker=ticker, quantity=10, avg_cost=100.0, currency=currency,
        account="taxable",
    )


# ---- build_chat_context -----------------------------------------------------


async def test_context_includes_positions_totals_and_digest(monkeypatch):
    market.cache_clear()
    monkeypatch.setattr(
        market,
        "_fetch_quote_raw",
        lambda t: {"last_price": 200.0, "previous_close": 190.0, "volume": 5},
    )
    # FakeRepo scopes positions to the owner user.
    uid = uuid.UUID(main.DEFAULT_USER_ID)
    repo = FakeRepo(positions=[_position()])
    today = datetime.now(timezone.utc).astimezone().date()
    repo._digests_by_user[(uid, today)] = SimpleNamespace(
        body="NVDA ran hot yesterday. " * 40, created_at=datetime.now(timezone.utc)
    )
    ctx = ToolContext(settings=get_settings(), repo=repo, user_id=uid)

    blob = await build_chat_context(ctx, tz="America/Toronto")
    data = json.loads(blob)

    assert data["positions"][0]["ticker"] == "NVDA"
    assert data["totals"]["total_market_value_cad"] is not None
    assert data["latest_digest"]["snippet"].startswith("NVDA ran hot")
    assert len(data["latest_digest"]["snippet"]) <= 400
    assert "today" in data


async def test_context_never_raises_and_returns_empty_when_bare():
    # No repo at all: portfolio and digest lookups both fail -> "".
    ctx = ToolContext(settings=get_settings(), repo=None)
    assert await build_chat_context(ctx, tz="not/a-zone") == ""


def test_compose_system_prompt_appends_context_block():
    assert compose_chat_system_prompt("BASE", "") == "BASE"
    composed = compose_chat_system_prompt("BASE", '{"positions": []}')
    assert composed.startswith("BASE")
    assert "<user_context>" in composed and "</user_context>" in composed


# ---- multi-turn memory --------------------------------------------------------


def test_build_initial_messages_prepends_history():
    history = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]
    msgs = build_initial_messages("q2", history)
    assert [m["content"] for m in msgs] == ["q1", "a1", "q2"]
    assert build_initial_messages("solo") == [{"role": "user", "content": "solo"}]


async def test_chat_history_messages_pairs_oldest_first_and_skips_errors():
    settings = get_settings()
    repo = FakeRepo()
    uid = uuid.uuid4()
    base = datetime.now(timezone.utc)
    for i, (status, answer) in enumerate([
        ("completed", "a-old"),      # oldest
        ("error", None),             # skipped: errored
        ("completed", None),         # skipped: no answer yet
        ("completed", "a-new" * 800),  # newest, long answer -> truncated
    ]):
        repo.runs[uuid.uuid4()] = {
            "trigger": "chat", "user_id": uid, "status": status,
            "user_message": f"q{i}", "final_answer": answer,
            "created_at": base + timedelta(minutes=i),
        }

    history = await main._chat_history_messages(repo, uid, settings)

    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]
    assert history[0]["content"] == "q0"
    assert history[1]["content"] == "a-old"
    assert history[2]["content"] == "q3"
    assert len(history[3]["content"]) == main._CHAT_HISTORY_MSG_CHARS


async def test_chat_history_disabled_with_zero_turns(monkeypatch):
    monkeypatch.setenv("CHAT_HISTORY_TURNS", "0")
    get_settings.cache_clear()
    try:
        repo = FakeRepo()
        uid = uuid.uuid4()
        repo.runs[uuid.uuid4()] = {
            "trigger": "chat", "user_id": uid, "status": "completed",
            "user_message": "q", "final_answer": "a",
            "created_at": datetime.now(timezone.utc),
        }
        assert await main._chat_history_messages(repo, uid, get_settings()) == []
    finally:
        get_settings.cache_clear()


# ---- request shape (history + cached system prompt) ----------------------------


async def test_run_agent_replays_history_and_caches_system(monkeypatch):
    client = ScriptedAnthropic([text_turn("answer")])
    repo = FakeRepo()
    budget = Budget(max_iterations=5, max_cost_usd=0.50, model="claude-sonnet-4-6")
    history = [
        {"role": "user", "content": "what is NVDA?"},
        {"role": "assistant", "content": "A chipmaker."},
    ]

    result = await run_agent(
        "and its beta?", trigger="chat", system_prompt=CHAT_SYSTEM_PROMPT,
        tools=CHAT_TOOLS, budget=budget, db=repo, client=client, history=history,
    )

    assert result.status == "completed"
    call = client.calls[0]
    # The loop mutates the live messages list after the call; the first three
    # entries are what was sent on iteration 1.
    assert [m["content"] for m in call["messages"][:3]] == [
        "what is NVDA?", "A chipmaker.", "and its beta?",
    ]
    # System is a cacheable block list with a breakpoint on the static prefix.
    assert call["system"][0]["text"] == CHAT_SYSTEM_PROMPT
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
