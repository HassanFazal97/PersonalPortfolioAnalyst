"""SMS delivery via the Twilio Messages API.

Plain httpx with basic auth — the official twilio SDK has no async client and
this is one form-encoded POST. Twilio error codes distinguish permanent
failures (21211 invalid number, 21610 recipient texted STOP, 21614 not a
mobile) from transient ones; 429/5xx retry.

Cost note: a 900-char digest is ~6 SMS segments (~$0.05 via a CA long code).
A future lever is sending a short summary + dashboard link instead.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.delivery.adapters.base import SendResult

# Twilio error codes that no amount of retrying will fix.
_PERMANENT_CODES = {21211, 21408, 21610, 21614}


class TwilioSMSAdapter:
    channel = "sms"

    def __init__(
        self,
        *,
        account_sid: str,
        auth_token: str,
        from_number: str,
        timeout: float = 10.0,
    ) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from = from_number
        self._timeout = timeout

    async def send(
        self, destination: str, body: str, payload: dict[str, Any]
    ) -> SendResult:
        url = (
            "https://api.twilio.com/2010-04-01/Accounts/"
            f"{self._account_sid}/Messages.json"
        )
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    url,
                    auth=(self._account_sid, self._auth_token),
                    data={"To": destination, "From": self._from, "Body": body},
                )
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=f"twilio request failed: {exc}")
        if resp.status_code in (200, 201):
            return SendResult(ok=True, provider_message_id=resp.json().get("sid"))
        code: int | None = None
        detail = ""
        try:
            data = resp.json()
            code = data.get("code")
            detail = data.get("message", "")
        except Exception:  # noqa: BLE001 - error body shape is best-effort
            pass
        transient = resp.status_code == 429 or resp.status_code >= 500
        permanent = (code in _PERMANENT_CODES) or not transient
        return SendResult(
            ok=False,
            error=f"twilio error {resp.status_code} (code {code}): {detail}".strip(),
            permanent=permanent,
        )
