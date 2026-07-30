"""No-card Pro trial: provisioning, effective plan, digest pause, resolution."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.billing as billing
import app.main as main
from app.agent.digest_pipeline import run_digest_pipeline
from app.config import DEFAULT_USER_ID, get_settings
from app.main import create_app
from app.plans import (
    digest_cadence_due,
    effective_plan,
    trial_active,
    trial_decision_pending,
    user_plan_and_tz,
)
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
_AUTH = {"Authorization": "Bearer test-token"}

_FUTURE = datetime.now(timezone.utc) + timedelta(days=5)
_PAST = datetime.now(timezone.utc) - timedelta(days=1)


def _client(monkeypatch, repo):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("STRIPE_PRICE_PRO_MONTHLY", "price_monthly")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://app.example.com")
    get_settings.cache_clear()
    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.macro_scheduler = None
    return TestClient(app)


def _as_user(monkeypatch, uid):
    monkeypatch.setattr(main, "_user_id", lambda request: uid)


# --- plan helpers (unit) --------------------------------------------------------


def test_trial_states():
    active = SimpleNamespace(plan="free", trial_ends_at=_FUTURE)
    lapsed = SimpleNamespace(plan="free", trial_ends_at=_PAST)
    paid = SimpleNamespace(plan="pro", trial_ends_at=_PAST)
    plain = SimpleNamespace(plan="free", trial_ends_at=None)

    assert trial_active(active) is True
    assert effective_plan(active) == "pro"
    assert trial_decision_pending(active) is False

    assert trial_active(lapsed) is False
    assert effective_plan(lapsed) == "free"
    assert trial_decision_pending(lapsed) is True  # digests paused

    # Paying settles the trial even if the timestamp lingers.
    assert trial_decision_pending(paid) is False
    assert effective_plan(paid) == "pro"

    assert trial_active(plain) is False
    assert trial_decision_pending(plain) is False
    assert effective_plan(plain) == "free"
    assert effective_plan(None) == "free"


def test_user_plan_and_tz_resolves_trial_to_pro():
    settings = SimpleNamespace(tz="America/Toronto")
    user = SimpleNamespace(
        plan="free", trial_ends_at=_FUTURE, timezone="America/Vancouver"
    )
    plan, tz = user_plan_and_tz(user, user_id=uuid.uuid4(), settings=settings)
    assert plan == "pro"
    assert tz == "America/Vancouver"


def test_trial_user_gets_daily_cadence():
    # Effective pro => weekday digests; the cadence rule itself is unchanged.
    from datetime import date

    tuesday = date(2026, 7, 21)
    assert digest_cadence_due("pro", tuesday) is True
    assert digest_cadence_due("free", tuesday) is False


# --- provisioning ---------------------------------------------------------------


async def test_signup_does_not_arm_trial():
    # The clock starts at the first portfolio sync (the first value moment),
    # not at signup: a user who signs up Monday and connects Friday should
    # still get all 7 Pro days.
    repo = FakeRepo()
    uid = await repo.get_or_create_user(auth_id=uuid.uuid4(), trial_days=7)
    user = await repo.get_user(uid)
    assert user.trial_ends_at is None
    assert effective_plan(user) == "free"


async def test_first_sync_arms_trial_exactly_once():
    repo = FakeRepo()
    uid = await repo.get_or_create_user(auth_id=uuid.uuid4())
    ends = await repo.maybe_start_trial(uid, 7)
    user = await repo.get_user(uid)
    assert ends is not None and user.trial_ends_at == ends
    assert trial_active(user) and effective_plan(user) == "pro"
    # A later sync never resets the clock...
    assert await repo.maybe_start_trial(uid, 7) is None
    assert (await repo.get_user(uid)).trial_ends_at == ends
    # ...and choosing Free then reconnecting can't re-arm a consumed trial.
    await repo.resolve_trial(uid)
    assert await repo.maybe_start_trial(uid, 7) is None
    assert (await repo.get_user(uid)).trial_ends_at is None


async def test_trial_disabled_or_paying_never_arms():
    repo = FakeRepo()
    uid = await repo.get_or_create_user(auth_id=uuid.uuid4())
    assert await repo.maybe_start_trial(uid, 0) is None
    pro = uuid.uuid4()
    repo.seed_user(pro, plan="pro")
    assert await repo.maybe_start_trial(pro, 7) is None


def test_decision_pending_is_grace_bounded():
    # The digests-paused forced-choice moment lasts TRIAL_DECISION_GRACE_DAYS;
    # after that the account silently resumes as plain Free (no DB write —
    # every consumer resolves through trial_decision_pending).
    from app.plans import TRIAL_DECISION_GRACE_DAYS

    now = datetime.now(timezone.utc)
    inside = SimpleNamespace(
        plan="free",
        trial_ends_at=now - timedelta(days=TRIAL_DECISION_GRACE_DAYS - 1),
    )
    past = SimpleNamespace(
        plan="free",
        trial_ends_at=now - timedelta(days=TRIAL_DECISION_GRACE_DAYS + 1),
    )
    assert trial_decision_pending(inside) is True
    assert trial_decision_pending(past) is False
    assert effective_plan(past) == "free"


async def _fake_sync(repo, *, user_id, refresh=True):
    return {"synced": 1}


def test_first_portfolio_sync_arms_trial_via_route(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    monkeypatch.setattr(main, "sync_brokerage_positions", _fake_sync)

    body = client.post("/portfolio/sync", headers=_AUTH).json()
    assert "trial_ends_at" in body
    user = repo._users_by_id[uid]
    assert trial_active(user)
    assert (uid, "portfolio_connected") in repo.funnel_events
    assert (uid, "trial_started") in repo.funnel_events
    # The second sync is just a sync — no trial fields in the response.
    assert "trial_ends_at" not in client.post("/portfolio/sync", headers=_AUTH).json()


# --- digest pipeline pause --------------------------------------------------------


async def test_digest_skipped_while_decision_pending():
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, trial_ends_at=_PAST)
    result = await run_digest_pipeline(repo, user_id=uid)
    assert result["status"] == "skipped_trial_decision"


async def test_digest_resumes_after_choosing_free():
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, trial_ends_at=_PAST)
    await repo.resolve_trial(uid)
    result = await run_digest_pipeline(repo, user_id=uid)
    assert result["status"] != "skipped_trial_decision"


# --- macro recipients --------------------------------------------------------------


async def test_macro_recipients_include_active_trials_only():
    repo = FakeRepo()
    trial_uid, lapsed_uid, free_uid, pro_uid = (uuid.uuid4() for _ in range(4))
    repo.seed_user(trial_uid, trial_ends_at=_FUTURE)
    repo.seed_user(lapsed_uid, trial_ends_at=_PAST)
    repo.seed_user(free_uid)
    repo.seed_user(pro_uid, plan="pro")
    recipients = await repo.list_macro_recipients()
    assert trial_uid in recipients
    assert pro_uid in recipients
    assert lapsed_uid not in recipients
    assert free_uid not in recipients


# --- chat quota ----------------------------------------------------------------------


def _quota_settings():
    return SimpleNamespace(
        free_monthly_cost_cap_usd=100.0,
        pro_monthly_cost_cap_usd=100.0,
        free_weekly_chat_limit=3,
        pro_daily_chat_limit=10,
    )


async def _burn_chats(repo, uid, n):
    for _ in range(n):
        await repo.create_run(
            trigger="chat", user_message="q", model="m",
            prompt_version="v", user_id=uid,
        )


async def test_trial_user_gets_pro_chat_quota():
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, trial_ends_at=_FUTURE)
    await _burn_chats(repo, uid, 3)  # over the Free weekly limit
    # Pro quota (10/day) still has room — no 402.
    await main._enforce_usage_limits(repo, uid, _quota_settings())


async def test_lapsed_trial_falls_back_to_free_quota():
    from fastapi import HTTPException

    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, trial_ends_at=_PAST)
    await _burn_chats(repo, uid, 3)
    with pytest.raises(HTTPException) as exc:
        await main._enforce_usage_limits(repo, uid, _quota_settings())
    assert exc.value.status_code == 402


# --- API surface -----------------------------------------------------------------------


def test_me_reports_trial_state(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, trial_ends_at=_FUTURE)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    body = client.get("/me", headers=_AUTH).json()
    assert body["plan"] == "free"
    assert body["effective_plan"] == "pro"
    assert body["trial"]["active"] is True
    assert body["trial"]["decision_pending"] is False
    assert body["trial"]["ends_at"] == _FUTURE.isoformat()
    assert body["digest_tickers_limit"] is None  # pro limits during trial


def test_me_reports_decision_pending(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, trial_ends_at=_PAST)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    body = client.get("/me", headers=_AUTH).json()
    assert body["effective_plan"] == "free"
    assert body["trial"]["decision_pending"] is True


def test_choose_free_resolves_trial(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, trial_ends_at=_PAST)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    body = client.post("/billing/choose-free", headers=_AUTH).json()
    assert body["trial"]["decision_pending"] is False
    assert body["trial"]["ends_at"] is None
    assert body["effective_plan"] == "free"


def test_checkout_allowed_during_trial(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, trial_ends_at=_FUTURE)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    class FakeClient:
        def __init__(self):
            ns = SimpleNamespace
            self.v1 = ns(
                customers=ns(create_async=self._customer),
                checkout=ns(sessions=ns(create_async=self._session)),
            )

        async def _customer(self, params=None, options=None):
            return SimpleNamespace(id="cus_trial")

        async def _session(self, params=None, options=None):
            return SimpleNamespace(url="https://checkout.stripe.com/c/cs_x")

    monkeypatch.setattr(billing, "get_client", lambda s: FakeClient())
    resp = client.post("/billing/checkout", headers=_AUTH, json={})
    assert resp.status_code == 200


async def test_paying_clears_trial_state():
    uid = uuid.uuid4()
    repo = FakeRepo()
    repo.seed_user(uid, trial_ends_at=_PAST, stripe_customer_id="cus_1")
    await billing.sync_subscription(repo, {
        "id": "sub_1",
        "customer": "cus_1",
        "status": "active",
        "metadata": {},
        "cancel_at_period_end": False,
        "items": {"data": [{"current_period_end": 1893456000}]},
    })
    user = await repo.get_user(uid)
    assert user.plan == "pro"
    assert user.trial_ends_at is None
    assert trial_decision_pending(user) is False
