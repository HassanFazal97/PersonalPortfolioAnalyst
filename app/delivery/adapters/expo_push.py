"""Push delivery via the Expo Push Service.

One HTTP call reaches both APNs and FCM, which is what makes push fit the
"one adapter = one provider HTTP call" shape of the other adapters — the APNs
key and FCM service account live in EAS, not in this container, so no new
credential and no new Python dependency (httpx is already a dep, and
requirements.txt is a hash-pinned lockfile).

Expo's ``DeviceNotRegistered`` maps exactly onto the dispatcher's
``permanent=True``: the token is dead (app uninstalled, or the OS rotated it)
and retrying it will never succeed.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.delivery.adapters.base import SendResult

_log = logging.getLogger(__name__)

PUSH_URL = "https://exp.host/--/api/v2/push/send"

# APNs and FCM both truncate long bodies anyway; a push is a pointer to
# content, not the content.
_MAX_BODY = 150

# Expo error codes that mean "never retry this token".
_PERMANENT_CODES = frozenset({"DeviceNotRegistered", "InvalidCredentials"})


class ExpoPushAdapter:
    channel = "push"

    def __init__(
        self,
        *,
        access_token: str = "",
        dry_run: bool = False,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._access_token = access_token
        self._dry_run = dry_run
        self._timeout = timeout
        self._transport = transport

    async def send(
        self, destination: str, body: str, payload: dict[str, Any]
    ) -> SendResult:
        if not destination.startswith(("ExponentPushToken[", "ExpoPushToken[")):
            return SendResult(
                ok=False, error="not an Expo push token", permanent=True
            )

        message = {
            "to": destination,
            "title": payload.get("title") or "Cirvia",
            "body": body[:_MAX_BODY],
            "sound": "default",
            # The real payload: what the tap should open. Kept small — APNs
            # caps the whole notification at ~4KB.
            "data": {
                "kind": payload.get("kind"),
                "deep_link": payload.get("deep_link"),
                "id": payload.get("id"),
            },
        }

        if self._dry_run:
            # The fan-out that queues these rows is the highest-consequence
            # edit in the delivery path, so it runs log-only first: the rows,
            # their destinations, and their bodies are all observable without
            # a single notification reaching a phone.
            _log.info("push dry-run: would send %s", message)
            return SendResult(ok=True, provider_message_id="dry-run")

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                resp = await client.post(PUSH_URL, json=message, headers=headers)
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=f"expo request failed: {exc}")

        if resp.status_code >= 400:
            # 4xx from Expo itself is a malformed request, not a dead token;
            # retrying a 5xx is worthwhile.
            return SendResult(
                ok=False,
                error=f"expo error {resp.status_code}",
                permanent=400 <= resp.status_code < 500,
            )

        try:
            ticket = (resp.json() or {}).get("data") or {}
        except ValueError:
            return SendResult(ok=False, error="expo returned a non-JSON body")

        # Expo answers 200 with a per-message ticket that can still be an
        # error — the status code alone does not mean delivered.
        if isinstance(ticket, list):
            ticket = ticket[0] if ticket else {}
        if ticket.get("status") == "error":
            code = ((ticket.get("details") or {}).get("error")) or ""
            return SendResult(
                ok=False,
                error=f"expo ticket error: {ticket.get('message') or code}",
                permanent=code in _PERMANENT_CODES,
            )

        return SendResult(ok=True, provider_message_id=ticket.get("id"))
