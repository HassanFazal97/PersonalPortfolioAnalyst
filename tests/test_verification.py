"""issue_code / check_code: rate limits, expiry, attempt caps, happy path."""

import re
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.delivery import verification
from app.delivery.adapters.base import SendResult
from app.delivery.verification import VerificationError, check_code, issue_code

USER = uuid.uuid4()
WEBHOOK = "https://discord.com/api/webhooks/1/x"


class FakeAdapter:
    channel = "discord"

    def __init__(self, ok=True):
        self.sent = []
        self._ok = ok

    async def send(self, destination, body, payload):
        self.sent.append(body)
        return SendResult(ok=self._ok, error=None if self._ok else "404")


class FakeVerificationRepo:
    def __init__(self):
        self.codes = {}
        self.channels = {}
        self.preferred = None

    async def count_verification_codes_since(self, since, *, destination=None, user_id=None):
        return sum(
            1
            for c in self.codes.values()
            if (destination is None or c.destination == destination)
            and (user_id is None or c.user_id == user_id)
            and c.created_at >= since
        )

    async def upsert_notification_channel(self, user_id, *, channel, destination, consent=False):
        self.channels[(user_id, channel)] = SimpleNamespace(
            destination=destination, verified_at=None, opted_out_at=None,
            consent_at=datetime.now(timezone.utc) if consent else None,
        )

    async def create_verification_code(self, user_id, *, channel, destination, code_hash, ttl_seconds=600):
        now = datetime.now(timezone.utc)
        for c in self.codes.values():
            if c.user_id == user_id and c.channel == channel and c.consumed_at is None:
                c.consumed_at = now
        code_id = uuid.uuid4()
        self.codes[code_id] = SimpleNamespace(
            id=code_id, user_id=user_id, channel=channel, destination=destination,
            code_hash=code_hash, expires_at=now + timedelta(seconds=ttl_seconds),
            attempts=0, consumed_at=None, created_at=now,
        )
        return code_id

    async def latest_verification_code(self, user_id, channel):
        now = datetime.now(timezone.utc)
        live = [
            c for c in self.codes.values()
            if c.user_id == user_id and c.channel == channel
            and c.consumed_at is None and c.expires_at > now
        ]
        return max(live, key=lambda c: c.created_at) if live else None

    async def record_code_attempt(self, code_id):
        self.codes[code_id].attempts += 1
        return self.codes[code_id].attempts

    async def consume_verification_code(self, code_id):
        self.codes[code_id].consumed_at = datetime.now(timezone.utc)

    async def mark_channel_verified(self, user_id, channel):
        row = self.channels.get((user_id, channel))
        if row is None:
            return False
        row.verified_at = datetime.now(timezone.utc)
        row.opted_out_at = None
        return True

    async def set_preferred_channel(self, user_id, channel):
        self.preferred = channel
        return True


def _extract_code(sent_body: str) -> str:
    match = re.search(r"\b(\d{6})\b", sent_body)
    assert match is not None, sent_body
    return match.group(1)


async def test_issue_then_verify_happy_path():
    repo, adapter = FakeVerificationRepo(), FakeAdapter()
    await issue_code(repo, {"discord": adapter}, USER, channel="discord", destination=WEBHOOK)
    assert (USER, "discord") in repo.channels
    code = _extract_code(adapter.sent[0])
    await check_code(repo, USER, channel="discord", code=code)
    assert repo.channels[(USER, "discord")].verified_at is not None
    assert repo.preferred == "discord"


async def test_issue_rejects_unconfigured_channel_and_bad_destination():
    repo = FakeVerificationRepo()
    with pytest.raises(VerificationError):
        await issue_code(repo, {}, USER, channel="sms", destination="+14165551234")
    with pytest.raises(VerificationError):
        await issue_code(
            repo, {"discord": FakeAdapter()}, USER,
            channel="discord", destination="https://evil.example/x",
        )


async def test_issue_rate_limits_per_destination():
    repo, adapter = FakeVerificationRepo(), FakeAdapter()
    for _ in range(verification.MAX_SENDS_PER_DESTINATION_PER_HOUR):
        await issue_code(repo, {"discord": adapter}, USER, channel="discord", destination=WEBHOOK)
    with pytest.raises(VerificationError) as exc:
        await issue_code(repo, {"discord": adapter}, USER, channel="discord", destination=WEBHOOK)
    assert exc.value.status_code == 429


async def test_issue_send_failure_surfaces_502():
    repo = FakeVerificationRepo()
    with pytest.raises(VerificationError) as exc:
        await issue_code(
            repo, {"discord": FakeAdapter(ok=False)}, USER,
            channel="discord", destination=WEBHOOK,
        )
    assert exc.value.status_code == 502


async def test_wrong_code_counts_attempts_then_locks():
    repo, adapter = FakeVerificationRepo(), FakeAdapter()
    await issue_code(repo, {"discord": adapter}, USER, channel="discord", destination=WEBHOOK)
    for _ in range(verification.MAX_CHECK_ATTEMPTS):
        with pytest.raises(VerificationError):
            await check_code(repo, USER, channel="discord", code="000000")
    with pytest.raises(VerificationError) as exc:
        await check_code(repo, USER, channel="discord", code="000000")
    assert exc.value.status_code == 429


async def test_expired_code_rejected():
    repo, adapter = FakeVerificationRepo(), FakeAdapter()
    await issue_code(repo, {"discord": adapter}, USER, channel="discord", destination=WEBHOOK)
    for c in repo.codes.values():
        c.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(VerificationError):
        await check_code(repo, USER, channel="discord", code="123456")


async def test_new_code_invalidates_previous():
    repo, adapter = FakeVerificationRepo(), FakeAdapter()
    await issue_code(repo, {"discord": adapter}, USER, channel="discord", destination=WEBHOOK)
    first = _extract_code(adapter.sent[0])
    await issue_code(repo, {"discord": adapter}, USER, channel="discord", destination=WEBHOOK)
    with pytest.raises(VerificationError):
        await check_code(repo, USER, channel="discord", code=first)
