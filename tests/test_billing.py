"""Stripe billing: webhook sync logic, checkout/portal routes, signatures."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.billing as billing
import app.main as main
from app.config import DEFAULT_USER_ID, get_settings
from app.main import create_app
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
_AUTH = {"Authorization": "Bearer test-token"}
WEBHOOK_SECRET = "whsec_test_secret"
BASE_URL = "https://app.example.com"


def _client(monkeypatch, repo, *, configured=True, annual=True):
    # No `with`: skip lifespan and inject the fake repo, as in tests/test_me.py.
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    if configured:
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
        monkeypatch.setenv("STRIPE_PRICE_PRO_MONTHLY", "price_monthly")
        if annual:
            monkeypatch.setenv("STRIPE_PRICE_PRO_ANNUAL", "price_annual")
        else:
            monkeypatch.setenv("STRIPE_PRICE_PRO_ANNUAL", "")
        monkeypatch.setenv("PUBLIC_BASE_URL", BASE_URL)
    else:
        # Empty-string overrides (not delenv): a developer .env with real
        # Stripe keys would otherwise leak into "unconfigured" tests, since
        # pydantic-settings reads the file when the process env has no value.
        for var in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
                    "STRIPE_PRICE_PRO_MONTHLY", "STRIPE_PRICE_PRO_ANNUAL"):
            monkeypatch.setenv(var, "")
    get_settings.cache_clear()
    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.macro_scheduler = None
    return TestClient(app)


def _as_user(monkeypatch, uid):
    """Route the request identity to a non-owner user (bearer binds owner)."""
    monkeypatch.setattr(main, "_user_id", lambda request: uid)


class FakeStripeClient:
    """The slice of stripe.StripeClient.v1 that app/billing.py touches."""

    def __init__(self, *, subscription=None):
        self.customers_created = []
        self.checkout_params = []
        self.portal_params = []
        self.canceled = []
        self.subscription = subscription
        ns = SimpleNamespace
        self.v1 = ns(
            customers=ns(create_async=self._create_customer),
            checkout=ns(sessions=ns(create_async=self._create_checkout)),
            billing_portal=ns(sessions=ns(create_async=self._create_portal)),
            subscriptions=ns(
                cancel_async=self._cancel, retrieve_async=self._retrieve
            ),
        )

    async def _create_customer(self, params=None, options=None):
        self.customers_created.append((params, options))
        return SimpleNamespace(id="cus_new")

    async def _create_checkout(self, params=None, options=None):
        self.checkout_params.append(params)
        return SimpleNamespace(url="https://checkout.stripe.com/c/cs_test")

    async def _create_portal(self, params=None, options=None):
        self.portal_params.append(params)
        return SimpleNamespace(url="https://billing.stripe.com/p/session")

    async def _cancel(self, subscription_id, params=None, options=None):
        self.canceled.append(subscription_id)
        return SimpleNamespace(id=subscription_id, status="canceled")

    async def _retrieve(self, subscription_id, params=None, options=None):
        return self.subscription


def _sub(status="active", *, sub_id="sub_1", customer="cus_1", metadata=None,
         cancel_at_period_end=False, period_end=1893456000, item_level=True):
    sub = {
        "id": sub_id,
        "customer": customer,
        "status": status,
        "metadata": metadata or {},
        "cancel_at_period_end": cancel_at_period_end,
    }
    if item_level:
        sub["items"] = {"data": [{"current_period_end": period_end}]}
    else:
        sub["current_period_end"] = period_end
    return sub


# --- plan_for_status (unit) ---------------------------------------------------


@pytest.mark.parametrize("status,plan", [
    ("active", "pro"),
    ("trialing", "pro"),
    ("past_due", "pro"),  # dunning grace while Smart Retries run
    ("canceled", "free"),
    ("unpaid", "free"),
    ("incomplete", "free"),
    ("incomplete_expired", "free"),
    ("paused", "free"),
    ("", "free"),
])
def test_plan_for_status(status, plan):
    assert billing.plan_for_status(status) == plan


# --- sync_subscription (unit) ---------------------------------------------------


async def test_sync_active_flips_to_pro():
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, stripe_customer_id="cus_1")
    await billing.sync_subscription(repo, _sub("active"))
    user = await repo.get_user(uid)
    assert user.plan == "pro"
    assert user.stripe_subscription_id == "sub_1"
    assert user.plan_since is not None
    assert user.stripe_current_period_end == datetime.fromtimestamp(
        1893456000, tz=timezone.utc
    )


async def test_sync_reads_top_level_period_end_fallback():
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, stripe_customer_id="cus_1")
    await billing.sync_subscription(repo, _sub("active", item_level=False))
    user = await repo.get_user(uid)
    assert user.stripe_current_period_end is not None


async def test_sync_canceled_downgrades_and_keeps_customer():
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, plan="pro", stripe_customer_id="cus_1",
                   stripe_subscription_id="sub_1")
    await billing.sync_subscription(repo, _sub("canceled"))
    user = await repo.get_user(uid)
    assert user.plan == "free"
    assert user.stripe_subscription_id is None
    assert user.stripe_current_period_end is None
    assert user.stripe_customer_id == "cus_1"  # re-subscribe reuses it


async def test_sync_cancel_at_period_end_stays_pro():
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, plan="pro", stripe_customer_id="cus_1",
                   stripe_subscription_id="sub_1")
    await billing.sync_subscription(repo, _sub("active", cancel_at_period_end=True))
    user = await repo.get_user(uid)
    assert user.plan == "pro"
    assert user.stripe_cancel_at_period_end is True


async def test_sync_unknown_customer_is_ignored():
    repo = FakeRepo()
    await billing.sync_subscription(repo, _sub("active", customer="cus_ghost"))
    # No user rows were created or modified.
    assert repo._users_by_id == {}


async def test_sync_falls_back_to_metadata_user_id_and_relinks():
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid)  # customer link lost / never stored
    await billing.sync_subscription(
        repo, _sub("active", metadata={"user_id": str(uid)})
    )
    user = await repo.get_user(uid)
    assert user.plan == "pro"
    assert user.stripe_customer_id == "cus_1"


async def test_sync_never_downgrades_owner():
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro", stripe_customer_id="cus_owner")
    await billing.sync_subscription(repo, _sub("canceled", customer="cus_owner"))
    assert (await repo.get_user(_OWNER)).plan == "pro"


async def test_sync_stale_subscription_cannot_downgrade():
    uid = uuid.uuid4()
    repo = FakeRepo()
    # User re-subscribed under sub_new; a terminal event for sub_old arrives late.
    repo.seed_user(uid, plan="pro", stripe_customer_id="cus_1",
                   stripe_subscription_id="sub_new")
    await billing.sync_subscription(repo, _sub("canceled", sub_id="sub_old"))
    user = await repo.get_user(uid)
    assert user.plan == "pro"
    assert user.stripe_subscription_id == "sub_new"


# --- checkout / portal routes ---------------------------------------------------


def test_checkout_requires_auth(monkeypatch):
    client = _client(monkeypatch, FakeRepo())
    assert client.post("/billing/checkout", json={}).status_code == 401


def test_checkout_503_when_unconfigured(monkeypatch):
    client = _client(monkeypatch, FakeRepo(), configured=False)
    resp = client.post("/billing/checkout", headers=_AUTH, json={})
    assert resp.status_code == 503


def test_checkout_owner_rejected(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    resp = _client(monkeypatch, repo).post(
        "/billing/checkout", headers=_AUTH, json={}
    )
    assert resp.status_code == 400


def test_checkout_already_pro_conflicts(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, plan="pro", stripe_customer_id="cus_1")
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    resp = client.post("/billing/checkout", headers=_AUTH, json={})
    assert resp.status_code == 409


def test_checkout_annual_unavailable(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid)
    client = _client(monkeypatch, repo, annual=False)
    _as_user(monkeypatch, uid)
    monkeypatch.setattr(billing, "get_client", lambda s: FakeStripeClient())
    resp = client.post(
        "/billing/checkout", headers=_AUTH, json={"interval": "annual"}
    )
    assert resp.status_code == 400


def test_checkout_happy_path_creates_and_stores_customer(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, email="user@example.com")
    fake = FakeStripeClient()
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    monkeypatch.setattr(billing, "get_client", lambda s: fake)
    resp = client.post(
        "/billing/checkout", headers=_AUTH, json={"interval": "monthly"}
    )
    assert resp.status_code == 200
    assert resp.json()["url"].startswith("https://checkout.stripe.com/")
    # Customer persisted before the session was created (retry-safe).
    assert repo._users_by_id[uid].stripe_customer_id == "cus_new"
    (customer_params, customer_opts) = fake.customers_created[0]
    assert customer_opts["idempotency_key"] == f"cirvia-customer-{uid}"
    params = fake.checkout_params[0]
    assert params["mode"] == "subscription"
    assert params["customer"] == "cus_new"
    assert params["line_items"] == [{"price": "price_monthly", "quantity": 1}]
    assert params["client_reference_id"] == str(uid)
    assert params["subscription_data"]["metadata"]["user_id"] == str(uid)
    assert params["success_url"].startswith(f"{BASE_URL}/app/settings?billing=success")
    assert "automatic_tax" not in params  # deferred until GST/HST registration


def test_checkout_reuses_existing_customer(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, stripe_customer_id="cus_existing")
    fake = FakeStripeClient()
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    monkeypatch.setattr(billing, "get_client", lambda s: fake)
    resp = client.post("/billing/checkout", headers=_AUTH, json={})
    assert resp.status_code == 200
    assert fake.customers_created == []
    assert fake.checkout_params[0]["customer"] == "cus_existing"


def test_portal_requires_billing_history(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    resp = client.post("/billing/portal", headers=_AUTH)
    assert resp.status_code == 409


def test_portal_happy_path(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, plan="pro", stripe_customer_id="cus_1")
    fake = FakeStripeClient()
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    monkeypatch.setattr(billing, "get_client", lambda s: fake)
    resp = client.post("/billing/portal", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["url"].startswith("https://billing.stripe.com/")
    assert fake.portal_params[0] == {
        "customer": "cus_1",
        "return_url": f"{BASE_URL}/app/settings",
    }


# --- webhook route ---------------------------------------------------------------


def _signed_headers(payload: bytes, *, secret=WEBHOOK_SECRET, timestamp=None):
    ts = timestamp if timestamp is not None else int(time.time())
    mac = hmac.new(
        secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    return {"Stripe-Signature": f"t={ts},v1={mac}"}


def _event(event_id="evt_1", event_type="customer.subscription.updated",
           obj=None) -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "object": "event",
            "type": event_type,
            "data": {"object": obj or {}},
        }
    ).encode()


def test_webhook_rejects_bad_signature(monkeypatch):
    client = _client(monkeypatch, FakeRepo())
    resp = client.post(
        "/webhooks/stripe",
        content=_event(),
        headers={"Stripe-Signature": "t=1,v1=deadbeef"},
    )
    assert resp.status_code == 400


def test_webhook_rejects_missing_signature(monkeypatch):
    client = _client(monkeypatch, FakeRepo())
    assert client.post("/webhooks/stripe", content=_event()).status_code == 400


def test_webhook_subscription_deleted_downgrades(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, plan="pro", stripe_customer_id="cus_1",
                   stripe_subscription_id="sub_1")
    client = _client(monkeypatch, repo)
    canceled = _sub("canceled")

    async def fake_fetch(settings, sub_id):
        assert sub_id == "sub_1"
        return canceled

    monkeypatch.setattr(billing, "fetch_subscription", fake_fetch)
    payload = _event(
        event_type="customer.subscription.deleted", obj={"id": "sub_1"}
    )
    # No bearer header: the signature is the auth (proves the exemption).
    resp = client.post(
        "/webhooks/stripe", content=payload, headers=_signed_headers(payload)
    )
    assert resp.status_code == 200
    user = repo._users_by_id[uid]
    assert user.plan == "free"
    assert user.stripe_customer_id == "cus_1"


def test_webhook_checkout_completed_links_and_upgrades(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid)
    client = _client(monkeypatch, repo)
    active = _sub("active")

    async def fake_fetch(settings, sub_id):
        return active

    monkeypatch.setattr(billing, "fetch_subscription", fake_fetch)
    payload = _event(
        event_type="checkout.session.completed",
        obj={
            "client_reference_id": str(uid),
            "customer": "cus_1",
            "subscription": "sub_1",
        },
    )
    resp = client.post(
        "/webhooks/stripe", content=payload, headers=_signed_headers(payload)
    )
    assert resp.status_code == 200
    user = repo._users_by_id[uid]
    assert user.plan == "pro"
    assert user.stripe_customer_id == "cus_1"


def test_webhook_duplicate_event_short_circuits(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, stripe_customer_id="cus_1")
    client = _client(monkeypatch, repo)
    calls = []

    async def fake_fetch(settings, sub_id):
        calls.append(sub_id)
        return _sub("active")

    monkeypatch.setattr(billing, "fetch_subscription", fake_fetch)
    payload = _event(obj={"id": "sub_1"})
    headers = _signed_headers(payload)
    first = client.post("/webhooks/stripe", content=payload, headers=headers)
    second = client.post("/webhooks/stripe", content=payload, headers=headers)
    assert first.status_code == second.status_code == 200
    assert second.json()["duplicate"] is True
    assert len(calls) == 1  # processed exactly once


def test_webhook_missing_subscription_is_acknowledged(monkeypatch):
    """An event whose subscription Stripe no longer knows must 200 (no-op),
    not 500 into a retry storm."""
    client = _client(monkeypatch, FakeRepo())

    async def fake_fetch(settings, sub_id):
        return None  # what fetch_subscription returns on resource_missing

    monkeypatch.setattr(billing, "fetch_subscription", fake_fetch)
    payload = _event(
        event_type="customer.subscription.updated", obj={"id": "sub_gone"}
    )
    resp = client.post(
        "/webhooks/stripe", content=payload, headers=_signed_headers(payload)
    )
    assert resp.status_code == 200


def test_webhook_failed_event_is_not_marked_processed(monkeypatch):
    """A 500 during handling must leave the event unrecorded so Stripe's
    retry is processed instead of short-circuiting as a duplicate."""
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, stripe_customer_id="cus_1")
    client = _client(monkeypatch, repo)
    attempts = []

    async def flaky_fetch(settings, sub_id):
        attempts.append(sub_id)
        if len(attempts) == 1:
            raise RuntimeError("transient stripe outage")
        return _sub("active")

    monkeypatch.setattr(billing, "fetch_subscription", flaky_fetch)
    payload = _event(obj={"id": "sub_1"})
    headers = _signed_headers(payload)
    with pytest.raises(RuntimeError):  # TestClient re-raises the app's 500
        client.post("/webhooks/stripe", content=payload, headers=headers)
    retry = client.post("/webhooks/stripe", content=payload, headers=headers)
    assert retry.status_code == 200
    assert "duplicate" not in retry.json()
    assert repo._users_by_id[uid].plan == "pro"  # the retry actually processed


def test_webhook_unknown_event_type_is_acknowledged(monkeypatch):
    client = _client(monkeypatch, FakeRepo())
    payload = _event(event_type="invoice.created", obj={"id": "in_1"})
    resp = client.post(
        "/webhooks/stripe", content=payload, headers=_signed_headers(payload)
    )
    assert resp.status_code == 200


# --- account deletion cancels the subscription ----------------------------------


def test_delete_me_cancels_active_subscription(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, plan="pro", stripe_customer_id="cus_1",
                   stripe_subscription_id="sub_1")
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    canceled = []

    async def fake_cancel(settings, subscription_id):
        canceled.append(subscription_id)

    monkeypatch.setattr(billing, "cancel_subscription", fake_cancel)
    resp = client.delete("/me", headers=_AUTH)
    assert resp.status_code == 200
    assert canceled == ["sub_1"]
    assert uid in repo.deleted_users


def test_delete_me_aborts_when_cancel_fails(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, plan="pro", stripe_customer_id="cus_1",
                   stripe_subscription_id="sub_1")
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    async def fake_cancel(settings, subscription_id):
        raise RuntimeError("stripe is down")

    monkeypatch.setattr(billing, "cancel_subscription", fake_cancel)
    resp = client.delete("/me", headers=_AUTH)
    assert resp.status_code == 502
    # No zombie: the account (and its data) is intact for a retry.
    assert uid in repo._users_by_id
    assert getattr(repo, "deleted_users", []) == []


def test_delete_me_without_subscription_skips_stripe(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    async def boom(settings, subscription_id):
        raise AssertionError("should not be called")

    monkeypatch.setattr(billing, "cancel_subscription", boom)
    assert client.delete("/me", headers=_AUTH).status_code == 200


# --- /me billing block ------------------------------------------------------------


def test_me_exposes_billing_state(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, plan="pro", stripe_customer_id="cus_1",
                   stripe_subscription_id="sub_1")
    repo._users_by_id[uid].stripe_cancel_at_period_end = True
    repo._users_by_id[uid].stripe_current_period_end = datetime(
        2026, 8, 20, tzinfo=timezone.utc
    )
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    body = client.get("/me", headers=_AUTH).json()
    assert body["billing"] == {
        "enabled": True,
        "annual_available": True,
        "has_billing_account": True,
        "cancel_at_period_end": True,
        "current_period_end": "2026-08-20T00:00:00+00:00",
    }


def test_me_billing_disabled_without_config(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    body = _client(monkeypatch, repo, configured=False).get(
        "/me", headers=_AUTH
    ).json()
    assert body["billing"]["enabled"] is False
