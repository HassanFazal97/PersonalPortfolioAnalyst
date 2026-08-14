"""API tests for the dashboard product-tour endpoint
(POST /me/tutorial/complete) and the tutorial block in the /me payload."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_USER_ID, get_settings
from app.main import create_app
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
_AUTH = {"Authorization": "Bearer test-token"}


def _client(monkeypatch, repo):
    # Same lifespan-skipping pattern as tests/test_profile_api.py.
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


def test_me_tutorial_defaults_false(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    body = _client(monkeypatch, repo).get("/me", headers=_AUTH).json()
    assert body["tutorial"] == {"completed": False}


def test_me_tutorial_false_without_user_row(monkeypatch):
    body = _client(monkeypatch, FakeRepo()).get("/me", headers=_AUTH).json()
    assert body["tutorial"] == {"completed": False}


def test_complete_is_idempotent_and_persists(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    client = _client(monkeypatch, repo)
    first = client.post(
        "/me/tutorial/complete", headers=_AUTH, json={"outcome": "completed"}
    )
    assert first.status_code == 200
    assert first.json()["tutorial"]["completed"] is True
    again = client.post(
        "/me/tutorial/complete", headers=_AUTH, json={"outcome": "completed"}
    )
    assert again.status_code == 200
    assert again.json()["tutorial"]["completed"] is True


def test_complete_defaults_outcome_and_records_funnel(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    client = _client(monkeypatch, repo)
    resp = client.post("/me/tutorial/complete", headers=_AUTH, json={})
    assert resp.status_code == 200
    assert repo.funnel_events[(_OWNER, "tutorial_completed")] == {
        "outcome": "completed"
    }


def test_skip_records_skipped_outcome(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    client = _client(monkeypatch, repo)
    resp = client.post(
        "/me/tutorial/complete", headers=_AUTH, json={"outcome": "skipped"}
    )
    assert resp.status_code == 200
    assert resp.json()["tutorial"]["completed"] is True
    assert repo.funnel_events[(_OWNER, "tutorial_completed")] == {
        "outcome": "skipped"
    }


@pytest.mark.parametrize("outcome", ["yolo", "", "done"])
def test_complete_rejects_unknown_outcome(monkeypatch, outcome):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    resp = _client(monkeypatch, repo).post(
        "/me/tutorial/complete", headers=_AUTH, json={"outcome": outcome}
    )
    assert resp.status_code == 400
