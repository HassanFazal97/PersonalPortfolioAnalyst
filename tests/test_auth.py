import base64
import hashlib
import hmac
import json
import time
import uuid
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm

import app.auth.jwt as auth_jwt
import app.main as main
from app.agent.budget import Budget
from app.agent.loop import run_agent
from app.auth.context import get_current_user_id, set_current_user_id
from app.auth.jwt import AuthError, verify_supabase_jwt
from app.config import get_settings
from app.main import create_app
from app.tools.registry import CHAT_TOOLS
from tests.fakes import FakeRepo, ScriptedAnthropic, text_turn

SECRET = "test-jwt-secret-with-at-least-32-bytes-of-length"
JWKS_URL = "https://project.supabase.co/auth/v1/.well-known/jwks.json"
TOKEN = "svc-token-abc"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_jwt(claims: dict, secret: str = SECRET, alg: str = "HS256") -> str:
    header = _b64(json.dumps({"alg": alg, "typ": "JWT"}).encode())
    payload = _b64(json.dumps(claims).encode())
    signing_input = f"{header}.{payload}".encode()
    if alg == "HS256":
        sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    else:
        sig = b"not-a-real-signature"
    return f"{header}.{payload}.{_b64(sig)}"


def _claims(**over):
    base = {
        "sub": str(uuid.uuid4()),
        "aud": "authenticated",
        "email": "user@example.com",
        "exp": int(time.time()) + 3600,
    }
    base.update(over)
    return base


def _es256_keypair(kid="kid-1"):
    priv = ec.generate_private_key(ec.SECP256R1())
    jwk = json.loads(ECAlgorithm.to_jwk(priv.public_key()))
    jwk.update({"kid": kid, "alg": "ES256", "use": "sig"})
    return priv, {"keys": [jwk]}, kid


def make_es256(claims, priv, kid):
    return pyjwt.encode(claims, priv, algorithm="ES256", headers={"kid": kid})


# ---- JWT verifier ---------------------------------------------------------


def test_verify_accepts_valid_token():
    claims = _claims()
    out = verify_supabase_jwt(make_jwt(claims), SECRET)
    assert out["sub"] == claims["sub"]
    assert out["email"] == "user@example.com"


def test_verify_rejects_bad_signature():
    with pytest.raises(AuthError):
        verify_supabase_jwt(make_jwt(_claims()), "wrong-secret")


def test_verify_rejects_expired():
    with pytest.raises(AuthError):
        verify_supabase_jwt(make_jwt(_claims(exp=int(time.time()) - 3600)), SECRET)


def test_verify_rejects_alg_none_and_rs256():
    # Algorithm is hard-pinned to HS256 — no downgrade/confusion.
    for alg in ("none", "RS256"):
        with pytest.raises(AuthError):
            verify_supabase_jwt(make_jwt(_claims(), alg=alg), SECRET)


def test_verify_rejects_wrong_audience():
    with pytest.raises(AuthError):
        verify_supabase_jwt(make_jwt(_claims(aud="anon")), SECRET, audience="authenticated")


def test_verify_rejects_missing_sub():
    claims = _claims()
    del claims["sub"]
    with pytest.raises(AuthError):
        verify_supabase_jwt(make_jwt(claims), SECRET)


# ---- ES256 via JWKS (the Supabase asymmetric default) ---------------------


def test_verify_accepts_es256_via_jwks(monkeypatch):
    auth_jwt.cache_clear()
    priv, jwks, kid = _es256_keypair()
    monkeypatch.setattr(auth_jwt, "_fetch_jwks", lambda url: jwks)
    claims = _claims()
    out = verify_supabase_jwt(make_es256(claims, priv, kid), jwks_url=JWKS_URL)
    assert out["sub"] == claims["sub"]


def test_verify_es256_rejects_unknown_kid(monkeypatch):
    auth_jwt.cache_clear()
    priv, jwks, _ = _es256_keypair(kid="kid-1")
    monkeypatch.setattr(auth_jwt, "_fetch_jwks", lambda url: jwks)
    with pytest.raises(AuthError):
        verify_supabase_jwt(make_es256(_claims(), priv, "kid-unknown"), jwks_url=JWKS_URL)


def test_verify_es256_rejects_wrong_signing_key(monkeypatch):
    auth_jwt.cache_clear()
    _, jwks_pub, kid = _es256_keypair(kid="kid-1")
    other_priv, _, _ = _es256_keypair(kid="kid-1")  # signs with a key not in JWKS
    monkeypatch.setattr(auth_jwt, "_fetch_jwks", lambda url: jwks_pub)
    with pytest.raises(AuthError):
        verify_supabase_jwt(make_es256(_claims(), other_priv, kid), jwks_url=JWKS_URL)


def test_verify_asymmetric_without_jwks_config():
    priv, _, kid = _es256_keypair()
    with pytest.raises(AuthError):
        verify_supabase_jwt(make_es256(_claims(), priv, kid), jwks_url=None)


# ---- user_id threading through run_agent ----------------------------------


async def test_run_agent_binds_and_records_user():
    set_current_user_id(None)
    repo = FakeRepo()
    client = ScriptedAnthropic([text_turn("done")])
    uid = uuid.uuid4()
    budget = Budget(max_iterations=5, max_cost_usd=1.0, model="claude-sonnet-4-6")

    result = await run_agent(
        "hi", trigger="chat", system_prompt="s", tools=CHAT_TOOLS,
        budget=budget, db=repo, client=client, user_id=uid,
    )
    assert repo.runs[result.run_id]["user_id"] == uid  # attributed
    assert get_current_user_id() == uid  # bound for RLS


# ---- require_auth dependency ----------------------------------------------


def _request(path="/chat", repo=None):
    return SimpleNamespace(
        url=SimpleNamespace(path=path),
        state=SimpleNamespace(),
        app=SimpleNamespace(state=SimpleNamespace(repo=repo)),
    )


def _creds(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _settings(**over):
    base = {
        "api_token": "svc-token",
        "supabase_url": "",
        "supabase_jwt_secret": "",
        "supabase_jwt_aud": "authenticated",
        "trial_days": 7,
    }
    base.update(over)
    return SimpleNamespace(**base)


async def test_require_auth_health_is_exempt(monkeypatch):
    # No credentials needed for the liveness probe.
    await main.require_auth(_request(path="/health"), None)


async def test_require_auth_service_token_binds_owner(monkeypatch):
    set_current_user_id(None)
    monkeypatch.setattr(main, "get_settings", lambda: _settings())
    req = _request()
    await main.require_auth(req, _creds("svc-token"))
    assert req.state.user_id == main._OWNER_USER_ID
    assert get_current_user_id() == main._OWNER_USER_ID


async def test_require_auth_rejects_bad_token(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: _settings())
    with pytest.raises(HTTPException) as exc:
        await main.require_auth(_request(), _creds("nope"))
    assert exc.value.status_code == 401


async def test_require_auth_jwt_provisions_user(monkeypatch):
    set_current_user_id(None)
    monkeypatch.setattr(main, "get_settings", lambda: _settings(supabase_jwt_secret=SECRET))
    repo = FakeRepo()
    claims = _claims()
    req = _request(repo=repo)

    await main.require_auth(req, _creds(make_jwt(claims)))

    # A fresh app user was provisioned for this Supabase identity.
    assert req.state.user_id == repo._users_by_auth[uuid.UUID(claims["sub"])]
    assert get_current_user_id() == req.state.user_id
    assert req.state.user_id != main._OWNER_USER_ID


async def test_require_auth_es256_jwt_provisions_user(monkeypatch):
    set_current_user_id(None)
    auth_jwt.cache_clear()
    priv, jwks, kid = _es256_keypair()
    monkeypatch.setattr(auth_jwt, "_fetch_jwks", lambda url: jwks)
    monkeypatch.setattr(
        main, "get_settings",
        lambda: _settings(supabase_url="https://project.supabase.co"),
    )
    repo = FakeRepo()
    claims = _claims()
    req = _request(repo=repo)

    await main.require_auth(req, _creds(make_es256(claims, priv, kid)))

    assert req.state.user_id == repo._users_by_auth[uuid.UUID(claims["sub"])]
    assert req.state.user_id != main._OWNER_USER_ID


async def test_require_auth_jwt_ignored_when_unconfigured(monkeypatch):
    # Single-user mode: only the service token works, JWTs are rejected.
    monkeypatch.setattr(main, "get_settings", lambda: _settings())
    with pytest.raises(HTTPException):
        await main.require_auth(_request(), _creds(make_jwt(_claims())))


# ---- /auth/whoami endpoint (end-to-end via TestClient) --------------------


def _env(monkeypatch, **over):
    monkeypatch.setenv("API_TOKEN", TOKEN)
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SUPABASE_URL", over.get("supabase_url", ""))
    get_settings.cache_clear()


def test_whoami_service_token_is_owner(monkeypatch):
    _env(monkeypatch)
    with TestClient(create_app()) as client:
        resp = client.get("/auth/whoami", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_owner"] is True
    assert body["user_id"] == str(main._OWNER_USER_ID)


def test_whoami_requires_auth(monkeypatch):
    _env(monkeypatch)
    with TestClient(create_app()) as client:
        assert client.get("/auth/whoami").status_code == 401


def test_whoami_jwt_resolves_user(monkeypatch):
    _env(monkeypatch, supabase_url="https://project.supabase.co")
    auth_jwt.cache_clear()  # avoid a JWKS entry cached by an earlier test
    priv, jwks, kid = _es256_keypair(kid="whoami-kid")
    monkeypatch.setattr(auth_jwt, "_fetch_jwks", lambda url: jwks)
    app = create_app()
    with TestClient(app) as client:
        app.state.repo = FakeRepo()  # inject (lifespan set it None without a DB)
        token = make_es256(_claims(email="jane@example.com"), priv, kid)
        resp = client.get("/auth/whoami", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_owner"] is False
    assert body["email"] == "jane@example.com"
    assert body["user_id"] != str(main._OWNER_USER_ID)
