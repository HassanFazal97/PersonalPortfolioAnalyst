"""Tests for the delivery adapter registry (app/delivery/adapters)."""

from app.config import Settings
from app.delivery.adapters import build_adapters


def test_email_adapter_registers_with_bare_address():
    settings = Settings(RESEND_API_KEY="key", EMAIL_FROM="digest@cirvia.ca")
    adapters = build_adapters(settings)
    assert "email" in adapters


def test_email_adapter_registers_with_display_name_format():
    settings = Settings(
        RESEND_API_KEY="key", EMAIL_FROM="Cirvia <digest@cirvia.ca>"
    )
    adapters = build_adapters(settings)
    assert "email" in adapters


def test_email_adapter_refuses_bare_display_name():
    # The real production bug: EMAIL_FROM="Portfolio Analyst" has no
    # "<addr@domain>" part — Resend rejects it on every send. The adapter
    # must not register rather than fail permanently on every real send.
    settings = Settings(RESEND_API_KEY="key", EMAIL_FROM="Portfolio Analyst")
    adapters = build_adapters(settings)
    assert "email" not in adapters


def test_email_adapter_absent_without_credentials():
    settings = Settings(RESEND_API_KEY="", EMAIL_FROM="")
    adapters = build_adapters(settings)
    assert "email" not in adapters


def test_discord_always_registers():
    settings = Settings()
    adapters = build_adapters(settings)
    assert "discord" in adapters
