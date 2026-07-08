"""Destination-ownership verification: issue and check one-time codes.

The same 6-digit-code flow covers all channels — the code is delivered through
the adapter being verified, so a successful verification also proves the send
path works. Codes are stored hashed with a short TTL; issuance is rate-limited
per destination and per user to block SMS-pumping abuse.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.delivery.adapters.base import ChannelAdapter
from app.delivery.channels import validate_destination

CODE_TTL_SECONDS = 600
MAX_CHECK_ATTEMPTS = 5
MAX_SENDS_PER_DESTINATION_PER_HOUR = 3
MAX_SENDS_PER_USER_PER_DAY = 10


class VerificationError(Exception):
    """User-facing verification failure; ``status_code`` maps to HTTP."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


async def issue_code(
    repo: Any,
    adapters: dict[str, ChannelAdapter],
    user_id: uuid.UUID,
    *,
    channel: str,
    destination: str,
    consent: bool = False,
) -> None:
    """Register the destination (unverified) and send it a one-time code."""
    adapter = adapters.get(channel)
    if adapter is None:
        raise VerificationError(f"channel '{channel}' is not available", 400)
    problem = validate_destination(channel, destination)
    if problem is not None:
        raise VerificationError(problem, 400)

    now = datetime.now(timezone.utc)
    per_dest = await repo.count_verification_codes_since(
        now - timedelta(hours=1), destination=destination
    )
    if per_dest >= MAX_SENDS_PER_DESTINATION_PER_HOUR:
        raise VerificationError("too many codes sent to this destination; try later", 429)
    per_user = await repo.count_verification_codes_since(
        now - timedelta(days=1), user_id=user_id
    )
    if per_user >= MAX_SENDS_PER_USER_PER_DAY:
        raise VerificationError("daily verification limit reached; try tomorrow", 429)

    await repo.upsert_notification_channel(
        user_id, channel=channel, destination=destination, consent=consent
    )

    code = f"{secrets.randbelow(1_000_000):06d}"
    await repo.create_verification_code(
        user_id,
        channel=channel,
        destination=destination,
        code_hash=_hash(code),
        ttl_seconds=CODE_TTL_SECONDS,
    )
    result = await adapter.send(
        destination,
        f"Your verification code is {code}. It expires in 10 minutes.",
        {"kind": "verification", "subject": "Your verification code"},
    )
    if not result.ok:
        raise VerificationError(
            f"could not reach that destination: {result.error}", 502
        )


async def check_code(
    repo: Any,
    user_id: uuid.UUID,
    *,
    channel: str,
    code: str,
) -> None:
    """Validate a submitted code; on success the channel becomes verified and
    the user's preferred channel."""
    live = await repo.latest_verification_code(user_id, channel)
    if live is None:
        raise VerificationError("no active code; request a new one", 400)
    if live.attempts >= MAX_CHECK_ATTEMPTS:
        raise VerificationError("too many wrong attempts; request a new code", 429)
    if not hmac.compare_digest(live.code_hash, _hash(code.strip())):
        attempts = await repo.record_code_attempt(live.id)
        remaining = max(MAX_CHECK_ATTEMPTS - attempts, 0)
        raise VerificationError(f"wrong code ({remaining} attempts left)", 400)

    await repo.consume_verification_code(live.id)
    if not await repo.mark_channel_verified(user_id, channel):
        raise VerificationError("channel is no longer registered", 400)
    await repo.set_preferred_channel(user_id, channel)
