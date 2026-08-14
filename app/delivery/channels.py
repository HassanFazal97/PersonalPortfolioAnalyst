"""Channel constants and destination validation shared by the delivery stack.

Pure functions/constants only — imported by the repo, adapters, API routes,
and web UI without dragging in provider SDKs or DB code.
"""

from __future__ import annotations

import re

# Channels a user can choose as their ONE preferred destination.
CHANNELS: tuple[str, ...] = ("sms", "email", "discord")

# Push is deliberately NOT in CHANNELS.
#
# `preferred_channel` resolves a single destination, so adding push here would
# let a user select it and thereby lose their email digest — and a ~4KB push
# payload cannot carry a digest anyway. Push is an additive fan-out: a pointer
# to content that rides alongside whatever the preferred channel does. It is
# still a valid `outbound_messages.channel` value, which is why the dispatcher
# and the adapter registry know the name even though the picker never shows it.
PUSH_CHANNEL = "push"

_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Exact-prefix allowlist doubles as an SSRF guard: we only ever POST
# user-supplied URLs that live under Discord's webhook path.
DISCORD_WEBHOOK_PREFIX = "https://discord.com/api/webhooks/"


def validate_destination(channel: str, destination: str) -> str | None:
    """Return a human-readable problem with the destination, or None if valid."""
    if channel == "sms":
        if not _E164_RE.match(destination):
            return "phone number must be in E.164 format, e.g. +14165551234"
    elif channel == "email":
        if not _EMAIL_RE.match(destination):
            return "not a valid email address"
    elif channel == "discord":
        if not destination.startswith(DISCORD_WEBHOOK_PREFIX):
            return f"Discord webhook URL must start with {DISCORD_WEBHOOK_PREFIX}"
    else:
        return f"unknown channel '{channel}'"
    return None


def mask_destination(channel: str, destination: str) -> str:
    """Mask a destination for display: +1•••••1234, f•••@gmail.com, •••/hook."""
    if channel == "sms":
        return destination[:2] + "•" * 5 + destination[-4:]
    if channel == "email":
        local, _, domain = destination.partition("@")
        return (local[:1] or "•") + "•••@" + domain
    if channel == "discord":
        return "discord webhook •••" + destination[-4:]
    if channel == PUSH_CHANNEL:
        # ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx] — show only the tail so a
        # device is identifiable in a list without exposing a sendable token.
        return "device •••" + destination.rstrip("]")[-4:]
    return "•••"
