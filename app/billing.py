"""Stripe billing: Checkout, Customer Portal, and the webhook sync.

Purchases run through hosted Stripe Checkout; self-serve manage/cancel runs
through the hosted Customer Portal. The webhook never trusts an event's
payload state — every event is a signal to re-fetch the subscription and sync
``users.plan`` to Stripe's *current* state, which makes duplicate and
out-of-order deliveries harmless. Nothing else in the app talks to Stripe.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from functools import lru_cache

import stripe
from fastapi import HTTPException

from app.config import DEFAULT_USER_ID, Settings

logger = logging.getLogger(__name__)

_OWNER_USER_ID = uuid.UUID(DEFAULT_USER_ID)

# Subscription statuses that keep Pro. past_due rides out Stripe's Smart
# Retries (dunning grace); the dashboard is configured to cancel after the
# final failed retry, which lands here as customer.subscription.deleted.
_PRO_STATUSES = frozenset({"active", "trialing", "past_due"})


def billing_enabled(settings: Settings) -> bool:
    """Whether Pro upgrades can be purchased on this deployment. The UI keeps
    its "coming soon" copy until all three are configured."""
    return bool(
        settings.stripe_secret_key
        and settings.stripe_price_pro_monthly
        and settings.public_base_url
    )


@lru_cache(maxsize=4)
def _client_for(api_key: str) -> stripe.StripeClient:
    return stripe.StripeClient(api_key, http_client=stripe.HTTPXClient())


def get_client(settings: Settings) -> stripe.StripeClient:
    return _client_for(settings.stripe_secret_key)


def plan_for_status(status: str) -> str:
    return "pro" if status in _PRO_STATUSES else "free"


def verify_webhook(payload: bytes, sig_header: str, secret: str) -> stripe.Event:
    """Verify the Stripe-Signature header; raises on any mismatch."""
    return stripe.Webhook.construct_event(payload, sig_header, secret)


def _price_for_interval(settings: Settings, interval: str) -> str:
    if interval == "monthly":
        return settings.stripe_price_pro_monthly
    if interval == "annual":
        if not settings.stripe_price_pro_annual:
            raise HTTPException(status_code=400, detail="annual billing is not available")
        return settings.stripe_price_pro_annual
    raise HTTPException(status_code=400, detail="interval must be 'monthly' or 'annual'")


async def _ensure_customer(repo, settings: Settings, user) -> str:
    """The user's Stripe customer id, creating (and storing) one if missing.

    The customer is created and persisted *before* Checkout so a retried
    request can't mint duplicates; ``set_stripe_customer_id`` is
    first-writer-wins for the same reason."""
    if user.stripe_customer_id:
        return user.stripe_customer_id
    client = get_client(settings)
    customer = await client.v1.customers.create_async(
        params={"email": user.email or None, "metadata": {"user_id": str(user.id)}},
        options={"idempotency_key": f"cirvia-customer-{user.id}"},
    )
    return await repo.set_stripe_customer_id(user.id, customer.id)


async def create_checkout_session(repo, settings: Settings, user, *, interval: str) -> str:
    """A hosted Checkout URL for upgrading this user to Pro."""
    price_id = _price_for_interval(settings, interval)
    customer_id = await _ensure_customer(repo, settings, user)
    base = settings.public_base_url.rstrip("/")
    client = get_client(settings)
    params: dict = {
        "mode": "subscription",
        "customer": customer_id,
        "line_items": [{"price": price_id, "quantity": 1}],
        # user_id travels on the session AND the subscription so the webhook
        # can resolve the user even if the customer link were ever lost.
        "client_reference_id": str(user.id),
        "metadata": {"user_id": str(user.id)},
        "subscription_data": {"metadata": {"user_id": str(user.id)}},
        "allow_promotion_codes": True,
        "success_url": f"{base}/app/settings?billing=success&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{base}/app/settings?billing=canceled",
    }
    if settings.stripe_automatic_tax:
        params["automatic_tax"] = {"enabled": True}
        params["customer_update"] = {"address": "auto"}
    session = await client.v1.checkout.sessions.create_async(params=params)
    return session.url


async def create_portal_session(settings: Settings, customer_id: str) -> str:
    """A hosted Customer Portal URL (invoices, payment method, cancel)."""
    base = settings.public_base_url.rstrip("/")
    client = get_client(settings)
    session = await client.v1.billing_portal.sessions.create_async(
        params={"customer": customer_id, "return_url": f"{base}/app/settings"}
    )
    return session.url


async def cancel_subscription(settings: Settings, subscription_id: str) -> None:
    """Immediately cancel a subscription (account deletion). No proration
    refund — refunds stay manual per the pricing FAQ."""
    client = get_client(settings)
    await client.v1.subscriptions.cancel_async(subscription_id)


def _as_dict(obj) -> dict:
    """A plain (recursive) dict from a StripeObject — the SDK's objects are
    attribute-accessed, not dicts, so normalize once at the boundary."""
    return obj.to_dict() if hasattr(obj, "to_dict") else dict(obj)


async def fetch_subscription(settings: Settings, subscription_id: str) -> dict:
    """Current subscription state from the Stripe API (canceled subs are
    still retrievable). Module-level so tests can monkeypatch it."""
    client = get_client(settings)
    return _as_dict(await client.v1.subscriptions.retrieve_async(subscription_id))


def _period_end(sub: dict) -> datetime | None:
    # API versions >= 2025-03-31 carry current_period_end on the subscription
    # item; older payloads carry it on the subscription itself.
    items = (sub.get("items") or {}).get("data") or []
    ts = items[0].get("current_period_end") if items else None
    if ts is None:
        ts = sub.get("current_period_end")
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


async def sync_subscription(repo, sub: dict) -> None:
    """Sync one user's plan to a subscription's current state."""
    customer_id = sub.get("customer") or ""
    user = (
        await repo.get_user_by_stripe_customer_id(customer_id)
        if customer_id
        else None
    )
    if user is None:
        # Fall back to the user_id stamped into subscription metadata at
        # checkout, then repair the customer link.
        raw_uid = (sub.get("metadata") or {}).get("user_id", "")
        try:
            uid = uuid.UUID(raw_uid)
        except ValueError:
            uid = None
        if uid is not None:
            if customer_id:
                await repo.set_stripe_customer_id(uid, customer_id)
            user = await repo.get_user(uid)
    if user is None:
        logger.warning(
            "stripe webhook for unknown customer %s (sub %s) — ignoring",
            customer_id,
            sub.get("id"),
        )
        return

    plan = plan_for_status(sub.get("status", ""))
    if plan == "free":
        if user.id == _OWNER_USER_ID:
            logger.warning("ignoring Stripe downgrade for the owner account")
            return
        # A terminal event from an old subscription must not downgrade a
        # user who has since re-subscribed under a new one.
        if user.stripe_subscription_id and user.stripe_subscription_id != sub.get("id"):
            logger.info(
                "ignoring stale subscription %s for user %s (current %s)",
                sub.get("id"),
                user.id,
                user.stripe_subscription_id,
            )
            return
    await repo.apply_subscription_state(
        user.id,
        plan=plan,
        subscription_id=sub.get("id"),
        current_period_end=_period_end(sub),
        cancel_at_period_end=bool(sub.get("cancel_at_period_end")),
    )


async def handle_event(repo, settings: Settings, event) -> None:
    """Process one verified webhook event (idempotency handled by caller)."""
    etype = event["type"]
    obj = _as_dict(event["data"]["object"])
    if etype == "checkout.session.completed":
        # Belt and suspenders: (re-)link the customer before syncing.
        raw_uid = obj.get("client_reference_id") or ""
        customer_id = obj.get("customer") or ""
        try:
            uid = uuid.UUID(raw_uid)
        except ValueError:
            uid = None
        if uid is not None and customer_id:
            await repo.set_stripe_customer_id(uid, customer_id)
        sub_id = obj.get("subscription")
        if sub_id:
            await sync_subscription(repo, await fetch_subscription(settings, sub_id))
    elif etype in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        await sync_subscription(repo, await fetch_subscription(settings, obj["id"]))
    else:
        logger.info("unhandled stripe event type %s — ignoring", etype)
