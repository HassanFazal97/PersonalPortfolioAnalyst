"""send_digest — the terminal tool of a digest run.

Exposed only to digest runs (never chat). Enforces the 900-char limit by
returning an error tool_result on violation (the model must shorten and retry).
On success it writes the ``digests`` row for today and, in Phase B, enqueues to
``outbound_messages`` for the Mac worker to deliver.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.config import get_settings

DIGEST_MAX_CHARS = 900

SEND_DIGEST_SCHEMA = {
    "name": "send_digest",
    "description": (
        "Deliver the finished morning digest to the user. Call this exactly once "
        "to finish. The body must be <= 900 characters of plain text (no "
        "markdown). If it is too long you will be asked to shorten and try again."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"body": {"type": "string"}},
        "required": ["body"],
    },
}


def _today(tz: str) -> Any:
    return datetime.now(ZoneInfo(tz)).date()


async def send_digest(payload: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    body = payload.get("body")
    if not isinstance(body, str) or not body.strip():
        raise ValueError("body must be a non-empty string")

    if len(body) > DIGEST_MAX_CHARS:
        # Not an exception: return an error so it becomes an is_error tool_result
        # and the model shortens on the next turn.
        raise ValueError(
            f"digest is {len(body)} chars; must be <= {DIGEST_MAX_CHARS}. "
            "Shorten it and call send_digest again."
        )

    if ctx is None or getattr(ctx, "repo", None) is None:
        raise RuntimeError("send_digest requires database access")

    settings = get_settings()
    digest_date = _today(settings.tz)
    run_id = getattr(ctx, "run_id", None)
    user_id = getattr(ctx, "user_id", None)

    await ctx.repo.upsert_digest(
        run_id=run_id, body=body, digest_date=digest_date, user_id=user_id
    )

    # Phase B: enqueue for the Mac worker. Harmless if no worker is running.
    if getattr(ctx, "enqueue_delivery", False):
        await ctx.repo.enqueue_outbound(body, user_id=user_id)

    return {
        "status": "sent",
        "digest_date": digest_date.isoformat(),
        "chars": len(body),
    }
