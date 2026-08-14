"""Suite-wide env isolation.

Tests must never read the developer's ``.env`` (or ``.env.prod``): historically
the suite leaked whatever pydantic-settings found there, which once included
production credentials. Two layers close that hole:

1. ``ENV_FILE`` is pointed at ``tests/env.test`` (safe placeholders) before any
   ``app.*`` import — ``app.config`` resolves ``ENV_FILE`` at import time.
2. Sensitive vars inherited from the invoking shell are scrubbed from the
   process env, because process env overrides the env file.

Live-DB tests opt in explicitly via ``TEST_DATABASE_URL`` (see
``test_tenant_isolation.py``); ``test_rls_policies.py`` provisions its own
throwaway container. Everything else runs offline.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ["ENV_FILE"] = str(Path(__file__).parent / "env.test")

_SCRUB = (
    "DATABASE_URL",
    "MIGRATION_DATABASE_URL",
    "SUPABASE_URL",
    "SUPABASE_JWT_SECRET",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "ANTHROPIC_API_KEY",
    "FINNHUB_API_KEY",
    "VOYAGE_API_KEY",
    "RESEND_API_KEY",
    "EMAIL_FROM",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_FROM_NUMBER",
    "SNAPTRADE_CLIENT_ID",
    "SNAPTRADE_CONSUMER_KEY",
    "SNAPTRADE_USER_ID",
    "SNAPTRADE_USER_SECRET",
    "BROKER_SECRETS_KEY",
    "DISCORD_CLIENT_ID",
    "DISCORD_CLIENT_SECRET",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "API_TOKEN",
)
for _key in _SCRUB:
    os.environ.pop(_key, None)

import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_settings_cache():
    """No test inherits another's cached Settings."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
