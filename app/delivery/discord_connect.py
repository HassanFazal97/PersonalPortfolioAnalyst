"""One-click Discord setup via OAuth2 ``webhook.incoming``.

Instead of pasting a webhook URL, the user is sent to Discord's authorize
page where Discord itself shows a server + channel picker. The token
exchange response contains a ready-made webhook URL, which we store as the
destination for the existing ``discord`` channel — delivery is unchanged.

The OAuth ``state`` is a signed, short-lived token minted for the signed-in
user: ``user_id:return_to:issued_unix:signature`` with an HMAC-SHA256
signature keyed by the same server-side secret as unsubscribe links. The
callback arrives as a bare browser redirect (no bearer token), so the state
is what proves which user initiated the connect.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx

from app.delivery.channels import DISCORD_WEBHOOK_PREFIX

AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
TOKEN_URL = "https://discord.com/api/oauth2/token"
STATE_TTL_SECONDS = 600

# Where the callback may send the browser afterwards, keyed by the short
# name the UI passes to connect-url. An allowlist — never a raw URL — so a
# forged state can't turn the callback into an open redirect.
RETURN_PATHS: dict[str, str] = {
    "settings": "/app/settings/delivery",
    "onboarding": "/app/onboarding",
}


class DiscordConnectError(Exception):
    """The code-for-webhook exchange failed; message is safe to log."""


def _sign(secret: str, payload: str) -> str:
    # Domain-separated from unsubscribe tokens, which share the secret.
    return hmac.new(
        secret.encode(), f"discord-oauth:{payload}".encode(), hashlib.sha256
    ).hexdigest()


def sign_state(secret: str, user_id: uuid.UUID, *, return_to: str) -> str:
    if return_to not in RETURN_PATHS:
        raise ValueError(f"unknown return_to '{return_to}'")
    payload = f"{user_id}:{return_to}:{int(time.time())}"
    return f"{payload}:{_sign(secret, payload)}"


def verify_state(
    secret: str, state: str, *, max_age_seconds: int = STATE_TTL_SECONDS
) -> tuple[uuid.UUID, str] | None:
    """Return (user_id, return_path) for a valid, fresh state, else None."""
    if not secret or not state:
        return None
    parts = state.split(":")
    if len(parts) != 4:
        return None
    user_part, return_to, issued_part, provided = parts
    payload = f"{user_part}:{return_to}:{issued_part}"
    if not hmac.compare_digest(_sign(secret, payload), provided):
        return None
    return_path = RETURN_PATHS.get(return_to)
    if return_path is None:
        return None
    try:
        user_id = uuid.UUID(user_part)
        issued = int(issued_part)
    except ValueError:
        return None
    if not 0 <= time.time() - issued <= max_age_seconds:
        return None
    return user_id, return_path


def authorize_url(client_id: str, *, redirect_uri: str, state: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "scope": "webhook.incoming",
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


async def exchange_code(
    client_id: str,
    client_secret: str,
    *,
    code: str,
    redirect_uri: str,
    timeout: float = 10.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Trade the authorization code for the webhook URL Discord created."""
    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            resp = await client.post(TOKEN_URL, data=data)
    except httpx.HTTPError as exc:
        raise DiscordConnectError(f"token request failed: {exc}") from exc
    if resp.status_code != 200:
        raise DiscordConnectError(f"token exchange rejected ({resp.status_code})")
    body: Any = resp.json()
    webhook_url = (body.get("webhook") or {}).get("url", "")
    if not webhook_url.startswith(DISCORD_WEBHOOK_PREFIX):
        raise DiscordConnectError("token response did not include a webhook URL")
    return webhook_url
