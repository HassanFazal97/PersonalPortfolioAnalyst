"""Pro-only web_search: server-block replay, pause_turn, and plan gating."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main
from app.agent.budget import Budget
from app.agent.loop import _block_to_dict, run_agent
from app.agent.prompts import CHAT_SYSTEM_PROMPT
from app.config import DEFAULT_USER_ID, get_settings
from app.main import create_app
from app.tools.registry import CHAT_TOOLS, WEB_SEARCH_TOOL
from tests.fakes import FakeRepo, ScriptedAnthropic, text_turn

_AUTH = {"Authorization": "Bearer test-token"}

_SERVER_TOOL_BLOCK = {
    "type": "server_tool_use",
    "id": "srvtoolu_1",
    "name": "web_search",
    "input": {"query": "TSX outlook"},
}
_SEARCH_RESULT_BLOCK = {
    "type": "web_search_tool_result",
    "tool_use_id": "srvtoolu_1",
    "content": [{"type": "web_search_result", "url": "https://example.com",
                 "title": "TSX outlook"}],
}


def test_block_to_dict_preserves_server_blocks_verbatim():
    assert _block_to_dict(_SERVER_TOOL_BLOCK) == _SERVER_TOOL_BLOCK
    assert _block_to_dict(_SEARCH_RESULT_BLOCK) == _SEARCH_RESULT_BLOCK


async def test_pause_turn_resends_conversation_and_completes():
    paused = {
        "stop_reason": "pause_turn",
        "content": [_SERVER_TOOL_BLOCK, _SEARCH_RESULT_BLOCK],
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }
    client = ScriptedAnthropic([paused, text_turn("Markets look calm.")])
    repo = FakeRepo()
    budget = Budget(max_iterations=5, max_cost_usd=0.50, model="claude-sonnet-4-6")

    result = await run_agent(
        "how are markets?", trigger="chat", system_prompt=CHAT_SYSTEM_PROMPT,
        tools=[*CHAT_TOOLS, WEB_SEARCH_TOOL], budget=budget, db=repo,
        client=client,
    )

    assert result.status == "completed"
    assert result.answer == "Markets look calm."
    assert len(client.calls) == 2
    # The paused assistant turn replays verbatim on the continuation call.
    replayed = client.calls[1]["messages"][1]
    assert replayed["role"] == "assistant"
    assert replayed["content"] == [_SERVER_TOOL_BLOCK, _SEARCH_RESULT_BLOCK]


def _client(monkeypatch, repo):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    get_settings.cache_clear()
    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.macro_scheduler = None
    return TestClient(app)


def _fake_run_agent(monkeypatch, repo, capture):
    async def fake(message, *, tools, trigger, user_id, **kwargs):
        capture["tools"] = tools
        capture["system_prompt"] = kwargs.get("system_prompt")
        run_id = uuid.uuid4()
        repo.runs[run_id] = {
            "trigger": trigger, "user_id": user_id, "status": "completed",
            "created_at": datetime.now(timezone.utc),
        }
        return SimpleNamespace(
            run_id=run_id, answer="ok", status="completed", iterations=1,
            input_tokens=1, output_tokens=1, cost_usd=0.0, latency_ms=1,
            tool_summaries=[],
        )

    monkeypatch.setattr(main, "run_agent", fake)


def test_web_search_granted_to_pro_only(monkeypatch):
    for plan, expect_web in (("free", False), ("pro", True)):
        repo = FakeRepo()
        uid = uuid.uuid4()
        repo.seed_user(uid, plan=plan)
        client = _client(monkeypatch, repo)
        monkeypatch.setattr(main, "_user_id", lambda request: uid)
        capture = {}
        _fake_run_agent(monkeypatch, repo, capture)

        resp = client.post("/chat", json={"message": "hi"}, headers=_AUTH)
        assert resp.status_code == 200
        names = [t["name"] for t in capture["tools"]]
        assert ("web_search" in names) is expect_web


def test_owner_gets_web_search(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(uuid.UUID(DEFAULT_USER_ID), plan="pro")
    client = _client(monkeypatch, repo)
    capture = {}
    _fake_run_agent(monkeypatch, repo, capture)

    assert client.post("/chat", json={"message": "hi"}, headers=_AUTH).status_code == 200
    assert any(t["name"] == "web_search" for t in capture["tools"])
