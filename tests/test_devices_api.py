"""POST/DELETE /me/devices and PATCH /me/devices/kinds."""

import uuid

from fastapi.testclient import TestClient

import app.main as main
from app.config import get_settings
from app.delivery.adapters import build_adapters
from app.main import create_app
from tests.fakes import FakeRepo

_AUTH = {"Authorization": "Bearer test-token"}
TOKEN = "ExponentPushToken[aaaaaaaaaaaaaaaaaaaaaa]"
OTHER = "ExponentPushToken[bbbbbbbbbbbbbbbbbbbbbb]"


def _client(monkeypatch, repo, **env):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.macro_scheduler = None
    # build_adapters normally runs in lifespan, which a bare TestClient never
    # enters; the other delivery suites wire it by hand the same way.
    app.state.delivery_adapters = build_adapters(get_settings())
    return app, TestClient(app)


def _as_user(monkeypatch, uid):
    monkeypatch.setattr(main, "_user_id", lambda request: uid)


def test_register_device(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    _, client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.post("/me/devices", json={"expo_token": TOKEN}, headers=_AUTH)

    assert resp.status_code == 201
    devices = resp.json()["devices"]
    assert len(devices) == 1
    # The token itself is never echoed back — only a masked form.
    assert TOKEN not in resp.text
    assert devices[0]["masked"].startswith("device •••")
    assert devices[0]["kinds"] == ["digest", "alert", "deep_dive"]


def test_register_is_idempotent(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    _, client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    client.post("/me/devices", json={"expo_token": TOKEN}, headers=_AUTH)
    resp = client.post("/me/devices", json={"expo_token": TOKEN}, headers=_AUTH)

    assert len(resp.json()["devices"]) == 1


def test_register_rejects_a_non_expo_token(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    _, client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.post("/me/devices", json={"expo_token": "+14165551234"}, headers=_AUTH)

    assert resp.status_code == 400
    assert "Expo push token" in resp.json()["detail"]


def test_register_rejects_unknown_kinds(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    _, client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.post(
        "/me/devices",
        json={"expo_token": TOKEN, "kinds": ["digest", "everything"]},
        headers=_AUTH,
    )

    assert resp.status_code == 400
    assert "everything" in resp.json()["detail"]


def test_unregister_only_touches_your_own_device(monkeypatch):
    """A leaked token must not let anyone silence someone else's phone."""
    repo = FakeRepo()
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    repo.seed_user(mine)
    repo.seed_user(theirs)
    _, client = _client(monkeypatch, repo)

    _as_user(monkeypatch, theirs)
    client.post("/me/devices", json={"expo_token": OTHER}, headers=_AUTH)

    _as_user(monkeypatch, mine)
    resp = client.request(
        "DELETE", "/me/devices", json={"expo_token": OTHER}, headers=_AUTH
    )

    assert resp.status_code == 200
    assert repo._push_devices[OTHER].disabled_at is None


def test_unregister_disables_your_device(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    _, client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    client.post("/me/devices", json={"expo_token": TOKEN}, headers=_AUTH)
    resp = client.request(
        "DELETE", "/me/devices", json={"expo_token": TOKEN}, headers=_AUTH
    )

    assert resp.json()["devices"] == []
    assert repo._push_devices[TOKEN].disabled_at is not None


def test_patch_kinds(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    _, client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    client.post("/me/devices", json={"expo_token": TOKEN}, headers=_AUTH)
    resp = client.patch("/me/devices/kinds", json={"kinds": ["digest"]}, headers=_AUTH)

    assert resp.json()["devices"][0]["kinds"] == ["digest"]


def test_push_is_never_offered_as_a_delivery_channel(monkeypatch):
    """The picker must not list push: choosing it would replace the user's
    preferred channel, and a 4KB payload cannot carry a digest."""
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    _, client = _client(monkeypatch, repo, PUSH_ENABLED="true")
    _as_user(monkeypatch, uid)

    body = client.get("/me/notifications", headers=_AUTH).json()

    assert "push" not in body["available_channels"]


def test_push_adapter_registers_only_when_enabled(monkeypatch):
    repo = FakeRepo()
    app_off, _ = _client(monkeypatch, repo)
    assert "push" not in app_off.state.delivery_adapters

    app_on, _ = _client(monkeypatch, repo, PUSH_ENABLED="true")
    assert "push" in app_on.state.delivery_adapters


def test_push_defaults_to_dry_run(monkeypatch):
    """The fan-out edits the one function whose silent failure means nobody
    gets their digest, so push ships log-only until explicitly turned live."""
    repo = FakeRepo()
    app_on, _ = _client(monkeypatch, repo, PUSH_ENABLED="true")

    assert app_on.state.delivery_adapters["push"]._dry_run is True


def test_devices_require_auth(monkeypatch):
    repo = FakeRepo()
    _, client = _client(monkeypatch, repo)

    assert client.post("/me/devices", json={"expo_token": TOKEN}).status_code == 401
