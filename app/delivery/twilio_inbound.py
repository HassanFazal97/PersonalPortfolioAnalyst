"""Inbound Twilio SMS webhook handling: signature validation + STOP/HELP/START.

Twilio signs webhooks with HMAC-SHA1 over the full request URL concatenated
with the sorted form parameters (key+value pairs), keyed by the account auth
token — ~15 lines, so no need for the (sync-only) twilio SDK. Opt-out keywords
set ``opted_out_at`` on the matching sms registration; Twilio's carrier-level
Advanced Opt-Out already sends the mandated STOP confirmation, so we only
record state and answer HELP.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any

# Keyword sets per Twilio/carrier conventions; matched against the whole
# trimmed message, case-insensitive.
STOP_WORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
START_WORDS = {"START", "UNSTOP", "YES"}
HELP_WORDS = {"HELP", "INFO"}

EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response/>'
HELP_TWIML = (
    '<?xml version="1.0" encoding="UTF-8"?><Response><Message>'
    "Portfolio Analyst: daily portfolio digests and alerts. "
    "Reply STOP to unsubscribe, START to resume. Support: see the dashboard."
    "</Message></Response>"
)


def compute_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    payload = url + "".join(k + v for k, v in sorted(params.items()))
    digest = hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def signature_valid(
    auth_token: str, url: str, params: dict[str, str], provided: str
) -> bool:
    if not auth_token or not provided:
        return False
    return hmac.compare_digest(compute_signature(auth_token, url, params), provided)


async def handle_inbound_sms(repo: Any, *, from_number: str, body: str) -> str:
    """Apply STOP/START/HELP state changes; returns the TwiML response body."""
    keyword = body.strip().upper()
    if keyword in STOP_WORDS:
        await repo.set_opt_out_by_destination(
            channel="sms", destination=from_number, opted_out=True
        )
        return EMPTY_TWIML
    if keyword in START_WORDS:
        await repo.set_opt_out_by_destination(
            channel="sms", destination=from_number, opted_out=False
        )
        return EMPTY_TWIML
    if keyword in HELP_WORDS:
        return HELP_TWIML
    return EMPTY_TWIML
