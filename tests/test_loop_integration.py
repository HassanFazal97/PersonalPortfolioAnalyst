import app.tools.market as market
from app.agent.budget import Budget
from app.agent.loop import run_agent
from app.agent.prompts import CHAT_SYSTEM_PROMPT
from app.tools.registry import CHAT_TOOLS
from tests.fakes import FakeRepo, ScriptedAnthropic, text_turn, tool_use_turn


async def test_three_turn_trajectory_with_one_erroring_tool(monkeypatch):
    market.cache_clear()
    # get_quote resolves offline; get_price_history(days=4) raises -> is_error.
    monkeypatch.setattr(
        market,
        "_fetch_quote_raw",
        lambda t: {"last_price": 200.0, "previous_close": 190.0, "volume": 5},
    )

    client = ScriptedAnthropic(
        [
            tool_use_turn("t1", "get_quote", {"tickers": ["NVDA"]}),
            tool_use_turn("t2", "get_price_history", {"ticker": "NVDA", "days": 4}),
            text_turn("NVDA is at 200, up 5.26% today."),
        ]
    )
    repo = FakeRepo()
    budget = Budget(max_iterations=10, max_cost_usd=0.50, model="claude-sonnet-4-6")

    result = await run_agent(
        "What's NVDA doing?",
        trigger="chat",
        system_prompt=CHAT_SYSTEM_PROMPT,
        tools=CHAT_TOOLS,
        budget=budget,
        db=repo,
        client=client,
    )

    # Terminal state
    assert result.status == "completed"
    assert result.answer == "NVDA is at 200, up 5.26% today."
    assert result.iterations == 3

    # All rows written
    assert len(repo.runs) == 1
    assert len(repo.model_calls) == 3
    assert len(repo.tool_calls) == 2

    # Error surfaced as is_error on the second tool, not the first
    quote_call = next(t for t in repo.tool_calls if t["tool_name"] == "get_quote")
    hist_call = next(t for t in repo.tool_calls if t["tool_name"] == "get_price_history")
    assert quote_call["is_error"] is False
    assert hist_call["is_error"] is True

    # Message assembly: the erroring tool_result was fed back with is_error=True
    turn3_messages = client.calls[2]["messages"]
    tool_results = [
        block
        for msg in turn3_messages
        if msg["role"] == "user" and isinstance(msg["content"], list)
        for block in msg["content"]
        if block.get("type") == "tool_result"
    ]
    assert any(tr["is_error"] for tr in tool_results)
    assert any(not tr["is_error"] for tr in tool_results)

    # Run finalized with correct token totals
    run = next(iter(repo.runs.values()))
    assert run["status"] == "completed"
    assert run["input_tokens"] == 300
    assert run["output_tokens"] == 60


async def test_budget_exceeded_ends_with_summary_turn(monkeypatch):
    market.cache_clear()
    monkeypatch.setattr(
        market,
        "_fetch_quote_raw",
        lambda t: {"last_price": 1.0, "previous_close": 1.0, "volume": 1},
    )

    # Model keeps requesting tools; cost cap is tiny so it breaches after turn 1.
    client = ScriptedAnthropic(
        [
            tool_use_turn("t1", "get_quote", {"tickers": ["NVDA"]}, in_tok=1_000_000, out_tok=0),
            text_turn("Summary: NVDA at 1.0."),  # the forced tools-off summary
        ]
    )
    repo = FakeRepo()
    budget = Budget(max_iterations=10, max_cost_usd=0.10, model="claude-sonnet-4-6")

    result = await run_agent(
        "loop forever",
        trigger="chat",
        system_prompt=CHAT_SYSTEM_PROMPT,
        tools=CHAT_TOOLS,
        budget=budget,
        db=repo,
        client=client,
    )

    assert result.status == "budget_exceeded"
    assert result.answer == "Summary: NVDA at 1.0."
    # Final summary call was made WITHOUT tools
    assert "tools" not in client.calls[-1]
