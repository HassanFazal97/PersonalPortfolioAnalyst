"""Signed unsubscribe links for email (CASL) — no DB storage needed.

The token is ``user_id:channel:signature`` where the signature is
HMAC-SHA256 over ``user_id:channel`` keyed by a server-side secret
(``UNSUBSCRIBE_SECRET``, falling back to ``API_TOKEN``). Stable per
(user, channel), verifiable statelessly, and unforgeable without the
secret. GET/POST /unsubscribe verifies it and opts the channel out via
the same repo path the Twilio STOP webhook uses.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from urllib.parse import quote

from app.config import Settings
from app.landing import _CSS, _FONT_LINKS


def unsubscribe_secret(settings: Settings) -> str:
    """The HMAC key. Dedicated secret preferred; API_TOKEN keeps small
    deployments working without another env var."""
    return settings.unsubscribe_secret or settings.api_token


def sign_token(secret: str, user_id: uuid.UUID, channel: str) -> str:
    payload = f"{user_id}:{channel}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_token(secret: str, token: str) -> tuple[uuid.UUID, str] | None:
    """Return (user_id, channel) for a valid token, else None."""
    if not secret or not token:
        return None
    parts = token.split(":")
    if len(parts) != 3:
        return None
    user_part, channel, provided = parts
    expected = hmac.new(
        secret.encode(), f"{user_part}:{channel}".encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, provided):
        return None
    try:
        return uuid.UUID(user_part), channel
    except ValueError:
        return None


def unsubscribe_url(
    settings: Settings, user_id: uuid.UUID, channel: str
) -> str | None:
    """Absolute unsubscribe link, or None when the deployment can't mint one
    (no public base URL or no secret configured)."""
    secret = unsubscribe_secret(settings)
    base = settings.public_base_url.rstrip("/")
    if not secret or not base:
        return None
    token = sign_token(secret, user_id, channel)
    return f"{base}/unsubscribe?token={quote(token, safe='')}"


# --- confirmation pages (marketing aesthetic, standalone) --------------------


def _page(title: str, heading: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{title}</title>
{_FONT_LINKS}<style>{_CSS}</style></head><body>
<main class="wrap" style="text-align:center;padding-top:5rem;max-width:560px;">
<a class="logo" href="/">Cir<span>via</span></a>
<h1 style="margin-top:2.5rem;">{heading}</h1>
<p class="lead" style="margin:1rem auto;">{body_html}</p>
</main></body></html>"""


UNSUBSCRIBED_HTML = _page(
    "Unsubscribed — Cirvia",
    "You're unsubscribed.",
    "Digests stop immediately. You can turn delivery back on anytime from "
    'your <a href="/app/dashboard">dashboard</a>.',
)

INVALID_LINK_HTML = _page(
    "Link not valid — Cirvia",
    "This link isn't valid.",
    "The unsubscribe link is invalid or has expired. You can manage delivery "
    'from your <a href="/app/dashboard">dashboard</a> instead.',
)
