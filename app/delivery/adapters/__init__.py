"""Adapter registry: which channels this deployment can actually send.

An adapter registers only when its provider credentials are configured, so an
unset provider simply hides that channel (the UI reads the configured set via
GET /me/notifications). Discord needs no global creds — the per-user webhook
URL is the whole integration.
"""

from __future__ import annotations

from app.config import Settings
from app.delivery.adapters.base import ChannelAdapter, SendResult
from app.delivery.adapters.discord import DiscordAdapter
from app.delivery.adapters.email_resend import ResendEmailAdapter
from app.delivery.adapters.twilio_sms import TwilioSMSAdapter

__all__ = ["ChannelAdapter", "SendResult", "build_adapters"]


def build_adapters(settings: Settings) -> dict[str, ChannelAdapter]:
    adapters: dict[str, ChannelAdapter] = {"discord": DiscordAdapter()}
    if settings.resend_api_key and settings.email_from:
        adapters["email"] = ResendEmailAdapter(
            api_key=settings.resend_api_key, from_addr=settings.email_from
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
    return adapters
