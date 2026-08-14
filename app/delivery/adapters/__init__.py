"""Adapter registry: which channels this deployment can actually send.

An adapter registers only when its provider credentials are configured, so an
unset provider simply hides that channel (the UI reads the configured set via
GET /me/notifications). Discord needs no global creds — the per-user webhook
URL is the whole integration.
"""

from __future__ import annotations

import logging
import re

from app.config import Settings
from app.delivery.adapters.base import ChannelAdapter, SendResult
from app.delivery.adapters.discord import DiscordAdapter
from app.delivery.adapters.email_resend import ResendEmailAdapter
from app.delivery.adapters.expo_push import ExpoPushAdapter
from app.delivery.adapters.twilio_sms import TwilioSMSAdapter

__all__ = ["ChannelAdapter", "SendResult", "build_adapters"]

_logger = logging.getLogger(__name__)

# Accepts a bare address ("digest@cirvia.ca") or "Display Name <addr@domain>".
# Not full RFC 5322 — just enough to catch the shape Resend actually rejects
# (a display name with no "<addr@domain>" part, e.g. "Portfolio Analyst").
_EMAIL_FROM_RE = re.compile(
    r"^(?:[^<>]+<[^@<>\s]+@[^@<>\s]+\.[^@<>\s]+>|[^@<>\s]+@[^@<>\s]+\.[^@<>\s]+)$"
)


def _looks_like_valid_from(value: str) -> bool:
    return bool(_EMAIL_FROM_RE.match(value.strip()))


def build_adapters(settings: Settings) -> dict[str, ChannelAdapter]:
    adapters: dict[str, ChannelAdapter] = {"discord": DiscordAdapter()}
    if settings.resend_api_key and settings.email_from:
        if _looks_like_valid_from(settings.email_from):
            adapters["email"] = ResendEmailAdapter(
                api_key=settings.resend_api_key, from_addr=settings.email_from
            )
        else:
            # A doomed adapter is worse than no adapter: registering it would
            # let users verify the email channel and then have every send
            # fail permanently at Resend with no visible symptom. Refusing to
            # register drops "email" from available_channels until this is
            # fixed, and says why right here in the logs.
            _logger.warning(
                "EMAIL_FROM=%r is not a valid sender address ('Name "
                "<addr@domain>' or a bare address) — email delivery is "
                "disabled until it is fixed.",
                settings.email_from,
            )
    if (
        settings.twilio_account_sid
        and settings.twilio_auth_token
        and settings.twilio_from_number
    ):
        adapters["sms"] = TwilioSMSAdapter(
            account_sid=settings.twilio_account_sid,
            auth_token=settings.twilio_auth_token,
            from_number=settings.twilio_from_number,
        )
    if settings.push_enabled:
        # Registered under "push", which is deliberately not in CHANNELS — the
        # delivery picker filters it out, so it can never become a user's one
        # preferred destination. See app/delivery/channels.py.
        adapters["push"] = ExpoPushAdapter(
            access_token=settings.expo_access_token,
            dry_run=settings.push_dry_run,
        )
        if settings.push_dry_run:
            _logger.warning(
                "PUSH_ENABLED with PUSH_DRY_RUN — push rows will be queued and "
                "logged but no notification will reach a device. Unset "
                "PUSH_DRY_RUN once the fan-out has been observed in production."
            )
    return adapters
