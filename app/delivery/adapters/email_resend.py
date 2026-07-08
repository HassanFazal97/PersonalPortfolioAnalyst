"""Email delivery via Resend (https://resend.com) — one authenticated POST.

No SDK: the API is a single JSON endpoint, same httpx pattern as the SnapTrade
client. 429/5xx are retried; other errors (bad key, unverified domain,
rejected recipient) won't fix themselves and fail permanently.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.delivery.adapters.base import SendResult

_API_URL = "https://api.resend.com/emails"


class ResendEmailAdapter:
    channel = "email"

    def __init__(self, *, api_key: str, from_addr: str, timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._from = from_addr
        self._timeout = timeout

    async def send(
        self, destination: str, body: str, payload: dict[str, Any]
    ) -> SendResult:
        subject = payload.get("subject") or "Portfolio update"
        message: dict[str, Any] = {
            "from": self._from,
            "to": [destination],
            "subject": subject,
            "text": body,
        }
        # CASL/deliverability: every email carries a one-click unsubscribe —
        # a plain footer link plus the RFC 8058 headers mail clients surface.
        unsubscribe_url = payload.get("unsubscribe_url")
        if unsubscribe_url:
            message["text"] = (
                f"{body}\n\nTo stop receiving these emails, unsubscribe here: "
                f"{unsubscribe_url}"
            )
            message["headers"] = {
                "List-Unsubscribe": f"<{unsubscribe_url}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    _API_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=message,
                )
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=f"resend request failed: {exc}")
        if resp.status_code == 200:
            return SendResult(ok=True, provider_message_id=resp.json().get("id"))
        transient = resp.status_code == 429 or resp.status_code >= 500
        detail = ""
        try:
            detail = resp.json().get("message", "")
        except Exception:  # noqa: BLE001 - error body shape is best-effort
            pass
        return SendResult(
            ok=False,
            error=f"resend error {resp.status_code}: {detail}".strip(),
            permanent=not transient,
        )
