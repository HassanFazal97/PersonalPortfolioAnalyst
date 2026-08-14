"""One shared AsyncAnthropic client for every pipeline.

Six sibling ``_get_client`` factories used to build a fresh client (and pay a
fresh TLS handshake) before every LLM turn. They now all resolve here: one
client per api key, connection-pooled for process life, with an explicit
request timeout and retry budget — the SDK's 600 s default timeout is the
difference between a slow response and an apparently hung app.

Keyed by api key via lru_cache (the billing.py Stripe-client pattern) so
tests that flip settings still get a matching client.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.config import get_settings


@lru_cache(maxsize=4)
def _client_for(api_key: str, timeout: float, max_retries: int) -> Any:
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(
        api_key=api_key, timeout=timeout, max_retries=max_retries
    )


def shared_client() -> Any:
    s = get_settings()
    return _client_for(
        s.anthropic_api_key, s.anthropic_timeout_seconds, s.anthropic_max_retries
    )
