"""Discord delivery via a user-supplied webhook URL.

One unauthenticated POST per message — the webhook URL itself is the secret.
Discord caps messages at 2000 chars, so longer bodies are split; 401/403/404
mean the webhook was deleted or the URL is wrong (permanent failure).
"""

from __future__ import annotations

from typing import Any

import httpx

from app.delivery.adapters.base import SendResult
from app.delivery.channels import DISCORD_WEBHOOK_PREFIX

_MAX_CONTENT = 2000


def _chunk(body: str, size: int = _MAX_CONTENT) -> list[str]:
    return [body[i : i + size] for i in range(0, len(body), size)] or [""]


class DiscordAdapter:
    channel = "discord"

    def __init__(self, *, timeout: float = 10.0) -> None:
        self._timeout = timeout

    async def send(
        self, destination: str, body: str, payload: dict[str, Any]
    ) -> SendResult:
        if not destination.startswith(DISCORD_WEBHOOK_PREFIX):
            return SendResult(ok=False, error="invalid Discord webhook URL", permanent=True)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                for chunk in _chunk(body):
                    resp = await client.post(destination, json={"content": chunk})
                    if resp.status_code in (401, 403, 404):
                        return SendResult(
                            ok=False,
                            error=f"webhook rejected ({resp.status_code})",
                            permanent=True,
                        )
                    if resp.status_code >= 400:
                        return SendResult(
                            ok=False, error=f"discord error {resp.status_code}"
                        )
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=f"discord request failed: {exc}")
        return SendResult(ok=True)
