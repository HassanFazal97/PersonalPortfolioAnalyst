"""POST /chat/start + GET /chat/runs/{id}/events.

The pair the native client uses instead of POST /chat/stream: the run id comes
back before the run finishes, so an answer produced while the app was
backgrounded can still be collected.
"""

import json
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
    return app, TestClient(app)


def _as_user(monkeypatch, uid):
    monkeypatch.setattr(main, "_user_id", lambda request: uid)


def _fake_run_agent(monkeypatch, repo):
    """Stub agent that honours a caller-supplied run_id and emits events."""

    async def fake(message, *, trigger, user_id, on_event=None, run_id=None, **kwargs):
        rid = run_id or uuid.uuid4()
        repo.runs.setdefault(
            rid,
            {
                "trigger": trigger,
                "user_id": user_id,
                "status": "running",
                "created_at": datetime.now(timezone.utc),
            },
        )
        if on_event is not None:
            await on_event({"type": "run_start", "run_id": str(rid)})
            await on_event({"type": "text_delta", "text": "NVDA is "})
            await on_event({"type": "text_delta", "text": "up today."})
        repo.runs[rid]["status"] = "completed"
        return SimpleNamespace(
            run_id=rid, answer="NVDA is up today.", status="completed",
            iterations=2, input_tokens=10, output_tokens=5, cost_usd=0.001,
            latency_ms=20, tool_summaries=[{"tool_name": "get_quote"}],
        )

    monkeypatch.setattr(main, "run_agent", fake)


def _frames(body: str) -> list[tuple[str, str]]:
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


def test_start_returns_202_with_run_id(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    _, client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    _fake_run_agent(monkeypatch, repo)

    resp = client.post("/chat/start", json={"message": "how's NVDA?"}, headers=_AUTH)
    assert resp.status_code == 202
    body = resp.json()
    # The id must be a real, persisted run — that is what makes the answer
    # recoverable through GET /runs/{id} after the buffer is gone.
    run_id = uuid.UUID(body["run_id"])
    assert run_id in repo.runs
    assert repo.runs[run_id]["user_id"] == uid
    # Nothing else leaks out of the 202: the answer arrives over SSE.
    assert set(body) == {"run_id"}


def test_events_replays_a_finished_run(monkeypatch):
    """The backgrounding case: the run completes with nobody listening, and
    the client still gets every event plus the answer when it comes back."""
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    _, client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    _fake_run_agent(monkeypatch, repo)

    run_id = client.post(
        "/chat/start", json={"message": "how's NVDA?"}, headers=_AUTH
    ).json()["run_id"]

    resp = client.get(f"/chat/runs/{run_id}/events", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _frames(resp.text)
    assert events[0][0] == "chat_snapshot"
    snapshot = json.loads(events[0][1])
    assert snapshot["run_id"] == run_id
    assert snapshot["finished"] is True

    replayed = [e["type"] for e in snapshot["events"]]
    assert replayed[0] == "run_start"
    assert replayed.count("text_delta") == 2
    assert replayed[-1] == "done"

    # `done` is authoritative: the client discards accumulated deltas for it.
    done = snapshot["events"][-1]
    assert done["answer"] == "NVDA is up today."
    assert done["status"] == "completed"
    assert done["chat_quota"]["used"] == 1


def test_a_live_run_is_known_but_not_finished(monkeypatch):
    """A subscriber arriving before the run ends must be told the stream is
    still live, so it waits for the rest instead of closing on the snapshot.

    The broker is inspected directly: TestClient cancels the detached driver
    task between requests, so a run cannot actually be held in flight across
    two HTTP calls here.
    """
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    app, client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    _fake_run_agent(monkeypatch, repo)

    run_id = uuid.UUID(
        client.post("/chat/start", json={"message": "hi"}, headers=_AUTH).json()["run_id"]
    )
    broker = app.state.chat_broker

    # Re-open it to model the mid-run state the handler reads.
    broker.open(run_id)
    assert broker.is_known(run_id)
    assert not broker.is_finished(run_id)

    broker.publish(run_id, {"type": "text_delta", "text": "hi"})
    broker.close(run_id)
    assert broker.is_finished(run_id)


def test_second_concurrent_start_is_429(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    app, client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    _fake_run_agent(monkeypatch, repo)

    # Stand in for a run already in flight for this user.
    app.state.active_chats.add(uid)
    before = len(repo.runs)

    resp = client.post("/chat/start", json={"message": "two"}, headers=_AUTH)
    assert resp.status_code == 429
    assert "already running" in resp.json()["detail"]
    # Rejected before anything was created, and the other run's claim survives.
    assert len(repo.runs) == before
    assert uid in app.state.active_chats


def test_quota_exhausted_is_402_before_anything_starts(monkeypatch):
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
    before = len(repo.runs)
    _, client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.post("/chat/start", json={"message": "hello"}, headers=_AUTH)
    assert resp.status_code == 402
    # No run row was created for a request that never ran.
    assert len(repo.runs) == before
    # And the concurrency guard was released on the failure path.
    assert (
        client.post("/chat/start", json={"message": "hello"}, headers=_AUTH).status_code
        == 402
    )


def test_events_404_on_another_users_run(monkeypatch):
    repo = FakeRepo()
    owner = uuid.uuid4()
    intruder = uuid.uuid4()
    repo.seed_user(owner, plan="pro")
    repo.seed_user(intruder, plan="pro")
    _, client = _client(monkeypatch, repo)
    _as_user(monkeypatch, owner)
    _fake_run_agent(monkeypatch, repo)

    run_id = client.post(
        "/chat/start", json={"message": "mine"}, headers=_AUTH
    ).json()["run_id"]

    _as_user(monkeypatch, intruder)
    resp = client.get(f"/chat/runs/{run_id}/events", headers=_AUTH)
    # 404 not 403, so run ids can't be probed for existence.
    assert resp.status_code == 404
    assert resp.json()["detail"] == "run not found"


def test_events_404_on_unknown_run(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    _, client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.get(f"/chat/runs/{uuid.uuid4()}/events", headers=_AUTH)
    assert resp.status_code == 404


def test_error_mid_run_is_replayed_as_an_error_event(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    _, client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    async def exploding(message, *, on_event=None, run_id=None, **kwargs):
        if on_event is not None:
            await on_event({"type": "run_start", "run_id": str(run_id)})
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "run_agent", exploding)

    run_id = client.post(
        "/chat/start", json={"message": "hello"}, headers=_AUTH
    ).json()["run_id"]

    snapshot = json.loads(
        _frames(client.get(f"/chat/runs/{run_id}/events", headers=_AUTH).text)[0][1]
    )
    assert [e["type"] for e in snapshot["events"]][-1] == "error"
    assert snapshot["finished"] is True

    # Guard released after the failure: a follow-up start isn't 429'd.
    _fake_run_agent(monkeypatch, repo)
    assert (
        client.post("/chat/start", json={"message": "again"}, headers=_AUTH).status_code
        == 202
    )


def test_web_chat_stream_still_works(monkeypatch):
    """The web client keeps its own endpoint, unchanged, after the refactor
    that moved the shared turn body into _run_chat_turn."""
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    _, client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    _fake_run_agent(monkeypatch, repo)

    resp = client.post("/chat/stream", json={"message": "hi"}, headers=_AUTH)
    assert resp.status_code == 200
    events = _frames(resp.text)
    assert events[-1][0] == "done"
    assert json.loads(events[-1][1])["answer"] == "NVDA is up today."
