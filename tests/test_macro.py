import json
import uuid

import app.agent.macro.orchestrator as orch
from app.agent.budget import Budget
from app.agent.macro import specialists
from app.agent.macro.orchestrator import parse_alerts, run_macro_scan
from app.agent.macro.specialists import parse_events, run_specialist
from app.observability.logging import Observer
from tests.fakes import FakeRepo, ScriptedAnthropic, text_turn


def _pause_turn(**usage):
    return {
        "stop_reason": "pause_turn",
        "content": [{"type": "text", "text": ""}],
        "usage": {"input_tokens": usage.get("in_tok", 10), "output_tokens": usage.get("out_tok", 2)},
    }


def test_parse_events_tags_category_and_defaults_severity():
    text = json.dumps({"events": [
        {"title": "War escalates", "summary": "s", "themes": ["defense"], "severity": "high"},
        {"title": "Minor", "summary": "s"},  # missing severity -> medium
    ]})
    out = parse_events(text, "geopolitical")
    assert len(out) == 2
    assert out[0]["category"] == "geopolitical" and out[0]["severity"] == "high"
    assert out[1]["severity"] == "medium"


def test_parse_events_bad_json_is_empty():
    assert parse_events("not json", "monetary") == []


def test_parse_alerts_clamps_body_and_builds_fingerprint():
    text = json.dumps({"alerts": [
        {"category": "monetary", "severity": "high", "headline": "Fed hike",
         "body": "x" * 500, "tickers": ["NVDA"], "fingerprint": "Fed-Hike-Jul"},
    ]})
    out = parse_alerts(text)
    assert len(out) == 1
    assert len(out[0]["body"]) == 300
    assert out[0]["fingerprint"] == "monetary:fed-hike-jul"


def test_parse_alerts_falls_back_to_hashed_fingerprint():
    text = json.dumps({"alerts": [
        {"category": "energy", "severity": "low", "headline": "Oil spikes", "body": "b"},
    ]})
    out = parse_alerts(text)
    assert out[0]["fingerprint"].startswith("energy:")


async def test_run_specialist_handles_pause_turn():
    repo = FakeRepo()
    run_id = uuid.uuid4()
    observer = Observer(repo, run_id)
    budget = Budget(max_iterations=25, max_cost_usd=2.0, model="claude-sonnet-4-6")
    events_json = json.dumps({"events": [
        {"title": "Rate cut", "summary": "s", "themes": ["rates"], "severity": "high"}
    ]})
    client = ScriptedAnthropic([_pause_turn(), text_turn(events_json)])

    events = await run_specialist(
        client=client, model="claude-sonnet-4-6", observer=observer, budget=budget,
        category="monetary", today="2026-07-05", iteration_base=10,
    )
    assert len(client.calls) == 2  # paused once, then resumed
    assert events and events[0]["category"] == "monetary"
    assert len(repo.model_calls) == 2  # both turns logged
    # The web_search tool was offered on the request.
    assert client.calls[0]["tools"][0]["type"] == "web_search_20260209"


async def test_run_macro_scan_creates_and_enqueues_alerts(monkeypatch):
    repo = FakeRepo()

    async def fake_portfolio(payload, ctx):
        return {"positions": [{"ticker": "NVDA"}, {"ticker": "XOM"}]}

    monkeypatch.setattr(orch.portfolio, "get_portfolio", fake_portfolio)

    ev = json.dumps({"events": [
        {"title": "Event", "summary": "s", "themes": ["tech"], "severity": "high"}
    ]})
    alerts = json.dumps({"alerts": [
        {"category": "monetary", "severity": "high", "headline": "Fed holds",
         "body": "Fed held rates; watch your rate-sensitive names.",
         "tickers": ["NVDA"], "fingerprint": "fed-hold-jul"},
    ]})
    # 4 specialists (same response) + 1 synthesis.
    client = ScriptedAnthropic([text_turn(ev)] * len(specialists.CATEGORIES) + [text_turn(alerts)])

    result = await run_macro_scan(repo, client=client)

    assert result["status"] == "completed"
    assert result["events_found"] == len(specialists.CATEGORIES)
    assert len(result["alerts"]) == 1
    # Delivered: stored + enqueued to the outbound queue.
    assert repo.outbound == ["Fed held rates; watch your rate-sensitive names."]
    assert any(a.delivered for a in repo.alerts.values())
    # Run finalized as completed.
    assert list(repo.runs.values())[0]["status"] == "completed"


async def test_run_macro_scan_dedupes_repeat_events(monkeypatch):
    repo = FakeRepo()

    async def fake_portfolio(payload, ctx):
        return {"positions": [{"ticker": "NVDA"}]}

    monkeypatch.setattr(orch.portfolio, "get_portfolio", fake_portfolio)

    ev = json.dumps({"events": [{"title": "E", "summary": "s", "themes": ["x"], "severity": "high"}]})
    alerts = json.dumps({"alerts": [
        {"category": "energy", "severity": "high", "headline": "Oil shock",
         "body": "Oil jumped.", "tickers": ["NVDA"], "fingerprint": "oil-shock-jul"},
    ]})

    def fresh_client():
        return ScriptedAnthropic([text_turn(ev)] * len(specialists.CATEGORIES) + [text_turn(alerts)])

    first = await run_macro_scan(repo, client=fresh_client())
    second = await run_macro_scan(repo, client=fresh_client())

    assert len(first["alerts"]) == 1
    assert second["alerts"] == []  # same fingerprint -> not re-delivered
    assert repo.outbound == ["Oil jumped."]  # enqueued exactly once
