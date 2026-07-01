import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.repo import resolve_ack_status
from app.main import create_app
from tests.fakes import FakeRepo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "macworker"))

TOKEN = "test-secret-token"


def test_resolve_ack_status_retry_then_fail():
    assert resolve_ack_status("sent", 1, 3) == "sent"
    assert resolve_ack_status("failed", 1, 3) == "queued"  # retry
    assert resolve_ack_status("failed", 2, 3) == "queued"  # retry
    assert resolve_ack_status("failed", 3, 3) == "failed"  # give up


def _authed_client(monkeypatch, repo):
    monkeypatch.setenv("API_TOKEN", TOKEN)
    get_settings.cache_clear()
    client = TestClient(create_app())
    client.__enter__()
    client.app.state.repo = repo  # inject after lifespan startup
    return client


def _seed_message(repo, body):
    msg_id = uuid.uuid4()
    repo._outbox[msg_id] = SimpleNamespace(
        id=msg_id, body=body, status="queued", attempts=0
    )
    return msg_id


def test_outbox_poll_send_ack_cycle(monkeypatch):
    repo = FakeRepo()
    client = _authed_client(monkeypatch, repo)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        msg_id = _seed_message(repo, "digest body")

        pending = client.get("/outbox/pending", headers=headers).json()["messages"]
        assert len(pending) == 1
        assert pending[0]["body"] == "digest body"

        ack = client.post(
            f"/outbox/{msg_id}/ack", json={"status": "sent"}, headers=headers
        )
        assert ack.status_code == 200
        assert ack.json()["status"] == "sent"

        # No longer pending after a successful send.
        assert client.get("/outbox/pending", headers=headers).json()["messages"] == []
    finally:
        client.__exit__(None, None, None)


def test_outbox_ack_rejects_bad_status(monkeypatch):
    repo = FakeRepo()
    client = _authed_client(monkeypatch, repo)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        msg_id = _seed_message(repo, "x")
        resp = client.post(
            f"/outbox/{msg_id}/ack", json={"status": "bogus"}, headers=headers
        )
        assert resp.status_code == 400
    finally:
        client.__exit__(None, None, None)


def test_worker_drain_once(monkeypatch):
    import worker

    acks: list[tuple[str, str]] = []

    def fake_request(method, path, body=None):
        if method == "GET" and path == "/outbox/pending":
            return {"messages": [{"id": "m1", "body": "hello", "attempts": 0}]}
        if method == "POST" and path.endswith("/ack"):
            acks.append((path, body["status"]))
            return {}
        return {}

    monkeypatch.setattr(worker, "_request", fake_request)
    monkeypatch.setattr(worker, "_send_imessage", lambda body: True)

    count = worker.drain_once()
    assert count == 1
    assert acks == [("/outbox/m1/ack", "sent")]


def test_worker_reports_failed_when_send_fails(monkeypatch):
    import worker

    acks: list[str] = []

    def fake_request(method, path, body=None):
        if method == "GET":
            return {"messages": [{"id": "m1", "body": "hi", "attempts": 2}]}
        acks.append(body["status"])
        return {}

    monkeypatch.setattr(worker, "_request", fake_request)
    monkeypatch.setattr(worker, "_send_imessage", lambda body: False)

    worker.drain_once()
    assert acks == ["failed"]
