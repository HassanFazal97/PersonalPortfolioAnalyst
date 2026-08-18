"""Universal link / App Link association files.

Apple and Google fetch these unauthenticated, from a fixed path, and reject
anything that redirects or arrives with the wrong content type — so the
failure mode is silent: links simply open in the browser instead of the app.
"""

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from tests.fakes import FakeRepo

AASA = "/.well-known/apple-app-site-association"
ASSETLINKS = "/.well-known/assetlinks.json"


def _client(monkeypatch, **env):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    app = create_app()
    app.state.repo = FakeRepo()
    app.state.scheduler = None
    app.state.macro_scheduler = None
    return TestClient(app)


def test_aasa_is_public_and_json(monkeypatch):
    """No bearer token: Apple's fetcher has none and cannot be given one."""
    client = _client(monkeypatch, IOS_TEAM_ID="ABCDE12345")

    resp = client.get(AASA, follow_redirects=False)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json()["applinks"]["details"][0]["appID"] == "ABCDE12345.ca.cirvia.app"


def test_aasa_scopes_to_app_and_stocks_only(monkeypatch):
    """Marketing pages must stay in the browser: that is where a visitor
    converts, and where a subscription can legally be sold."""
    client = _client(monkeypatch, IOS_TEAM_ID="ABCDE12345")

    detail = client.get(AASA).json()["applinks"]["details"][0]

    # NOT entries first: legacy `paths` matching is first-match-wins too.
    assert detail["paths"] == [
        "NOT /app/reset",
        "NOT /app/auth/*",
        "/app/*",
        "/stocks/*",
    ]
    covered = {c.get("/") for c in detail["components"]}
    assert "/app/*" in covered and "/stocks/*" in covered
    # Nothing claims the root, /pricing, or /track-record.
    assert not any(
        (c.get("/") or "").startswith(("/pricing", "/track-record"))
        for c in detail["components"]
    )
    assert "/" not in covered


def test_aasa_excludes_the_password_reset_bridge(monkeypatch):
    """Supabase recovery lands on /app/reset (web) or /app/auth/bridge
    (mobile) with the token in the URL fragment. Fragments never reach the
    server, so those pages have to run their client-side bridges in the
    browser rather than being swallowed by the app."""
    client = _client(monkeypatch, IOS_TEAM_ID="ABCDE12345")

    detail = client.get(AASA).json()["applinks"]["details"][0]
    excluded = {c["/"] for c in detail["components"] if c.get("exclude")}

    assert "/app/reset*" in excluded
    assert "/app/auth/*" in excluded
    # And the exclusions must precede the broad /app/* rule, or they never apply.
    order = [c.get("/") for c in detail["components"]]
    assert order.index("/app/reset*") < order.index("/app/*")
    assert order.index("/app/auth/*") < order.index("/app/*")


def test_aasa_404s_when_no_team_id_is_configured(monkeypatch):
    """Better a clean 404 than an association file naming a team that cannot
    sign the app — Apple caches these."""
    client = _client(monkeypatch)

    assert client.get(AASA).status_code == 404


def test_assetlinks_lists_every_fingerprint(monkeypatch):
    """Play app-signing and the upload key are different certs; missing one
    breaks App Links for builds signed with it."""
    client = _client(
        monkeypatch, ANDROID_CERT_FINGERPRINTS="aa:bb:cc, dd:ee:ff"
    )

    body = client.get(ASSETLINKS, follow_redirects=False).json()

    assert body[0]["target"]["package_name"] == "ca.cirvia.app"
    assert body[0]["target"]["sha256_cert_fingerprints"] == ["AA:BB:CC", "DD:EE:FF"]
    assert body[0]["relation"] == ["delegate_permission/common.handle_all_urls"]


def test_assetlinks_404s_when_unconfigured(monkeypatch):
    client = _client(monkeypatch)

    assert client.get(ASSETLINKS).status_code == 404


def test_wellknown_paths_are_auth_exempt(monkeypatch):
    """The whole point: these must answer without credentials."""
    import app.main as main

    assert AASA in main._AUTH_EXEMPT_PATHS
    assert ASSETLINKS in main._AUTH_EXEMPT_PATHS
