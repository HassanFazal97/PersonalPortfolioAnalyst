"""POST /chat/stream: SSE framing, terminal done event, and pre-run 4xx."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main
from app.config import get_settings
from app.main import create_app
from tests.fakes import FakeRepo

_AUTH = {"Authorization": "Bearer test-token"}


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


def _as_user(monkeypatch, uid):
    monkeypatch.setattr(main, "_user_id", lambda request: uid)


def _fake_run_agent(monkeypatch, repo):
    """Stub that emits agent events through on_event before answering, the
    way the real loop would."""

    async def fake(message, *, trigger, user_id, on_event=None, **kwargs):
        run_id = uuid.uuid4()
        repo.runs[run_id] = {
            "trigger": trigger,
            "user_id": user_id,
            "status": "completed",
            "created_at": datetime.now(timezone.utc),
        }
        if on_event is not None:
            await on_event({"type": "run_start", "run_id": str(run_id)})
            await on_event(
                {
                    "type": "tool_start",
                    "name": "get_quote",
                    "label": "Fetching live quotes",
                    "input_summary": "NVDA",
                }
            )
            await on_event(
                {"type": "tool_end", "name": "get_quote", "ok": True, "latency_ms": 5}
            )
            await on_event({"type": "text_delta", "text": "NVDA is "})
            await on_event({"type": "text_delta", "text": "up today."})
        return SimpleNamespace(
            run_id=run_id, answer="NVDA is up today.", status="completed",
            iterations=2, input_tokens=10, output_tokens=5, cost_usd=0.001,
            latency_ms=20, tool_summaries=[{"tool_name": "get_quote"}],
        )

    monkeypatch.setattr(main, "run_agent", fake)


def _frames(body: str) -> list[tuple[str, str]]:
    """Parse SSE text into (event, data) tuples, skipping heartbeats."""
    out = []
    for frame in body.split("\n\n"):
        ev, data = None, ""
        for line in frame.split("\n"):
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
        if ev:
            out.append((ev, data))
    return out


def test_stream_happy_path_emits_steps_then_done(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    _fake_run_agent(monkeypatch, repo)

    resp = client.post("/chat/stream", json={"message": "how's NVDA?"}, headers=_AUTH)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers.get("x-accel-buffering") == "no"

    events = _frames(resp.text)
    names = [e for e, _ in events]
    assert "run_start" in names
    assert "tool_start" in names and "tool_end" in names
    assert names.count("text_delta") == 2
    assert names[-1] == "done"
    import json as _json

    done = _json.loads(events[-1][1])
    assert done["answer"] == "NVDA is up today."
    assert done["status"] == "completed"
    assert done["chat_quota"]["used"] == 1  # quota refreshed post-run


def test_stream_quota_exhausted_is_plain_402(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    limit = get_settings().free_weekly_chat_limit
    stamp = datetime.now(timezone.utc) - timedelta(hours=1)
    for _ in range(limit):
        repo.runs[uuid.uuid4()] = {
            "trigger": "chat", "user_id": uid, "status": "completed",
            "created_at": stamp,
        }
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.post("/chat/stream", json={"message": "hello"}, headers=_AUTH)
    assert resp.status_code == 402  # JSON error BEFORE any stream starts
    assert "free questions" in resp.json()["detail"]
    # The concurrency guard was released on the failure path
    resp2 = client.post("/chat/stream", json={"message": "hello"}, headers=_AUTH)
    assert resp2.status_code == 402


def test_stream_error_event_when_run_fails_midway(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    async def exploding(message, *, on_event=None, **kwargs):
        if on_event is not None:
            await on_event({"type": "run_start", "run_id": "x"})
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "run_agent", exploding)

    resp = client.post("/chat/stream", json={"message": "hello"}, headers=_AUTH)
    assert resp.status_code == 200
    events = _frames(resp.text)
    assert events[-1][0] == "error"
    # Guard released after the failure: a follow-up chat isn't 429'd
    _fake_run_agent(monkeypatch, repo)
    assert (
        client.post("/chat/stream", json={"message": "again"}, headers=_AUTH).status_code
        == 200
    )
