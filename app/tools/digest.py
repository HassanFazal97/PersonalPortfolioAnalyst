"""send_digest — the terminal tool of a digest run.

Exposed only to digest runs (never chat). Enforces the 1000-char limit and the
labeled-section structure (PORTFOLIO / TOP RISK / WATCH TODAY) by returning an
error tool_result on violation (the model must fix the body and retry).
On success it writes the ``digests`` row for today and enqueues to
``outbound_messages``; the queue resolves the user's preferred channel (or
records a skip when none is verified), so enqueueing is unconditional.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.config import get_settings

DIGEST_MAX_CHARS = 1000

SEND_DIGEST_SCHEMA = {
    "name": "send_digest",
    "description": (
        "Deliver the finished morning digest to the user. Call this exactly once "
        "to finish. The body must be <= 1000 characters of plain text (no "
        "markdown), starting with a 'PORTFOLIO:' line, containing a 'TOP RISK' "
        "section, and ending with a 'WATCH TODAY:' line. If it is too long or "
        "malformed you will be asked to fix it and try again."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"body": {"type": "string"}},
        "required": ["body"],
    },
}


def _today(tz: str) -> Any:
    return datetime.now(ZoneInfo(tz)).date()


def validate_digest_structure(body: str) -> str | None:
    """Return an error message when the required section labels are missing.

    Deliberately lenient — only the three labels that make the digest scannable
    are required, so a slightly off-spec but readable digest still ships.
    """
    nonempty = [ln.strip() for ln in body.strip().splitlines() if ln.strip()]
    if not nonempty or not nonempty[0].startswith("PORTFOLIO:"):
        return 'digest must start with a "PORTFOLIO:" line'
    if "TOP RISK" not in nonempty:
        return 'digest must contain a "TOP RISK" section label on its own line'
    if not nonempty[-1].startswith("WATCH TODAY:"):
        return 'digest must end with a "WATCH TODAY:" line'
    return None


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

    structure_err = validate_digest_structure(body)
    if structure_err is not None:
        raise ValueError(f"{structure_err}. Fix the sections and call send_digest again.")

    if ctx is None or getattr(ctx, "repo", None) is None:
        raise RuntimeError("send_digest requires database access")

    settings = get_settings()
    tz = getattr(ctx, "timezone", None) or settings.tz
    digest_date = _today(tz)
    run_id = getattr(ctx, "run_id", None)
    user_id = getattr(ctx, "user_id", None)

    await ctx.repo.upsert_digest(
        run_id=run_id, body=body, digest_date=digest_date, user_id=user_id
    )

    await ctx.repo.enqueue_outbound(
        body,
        user_id=user_id,
        kind="digest",
        subject=f"Your morning digest — {digest_date.strftime('%b %d')}",
    )

    return {
        "status": "sent",
        "digest_date": digest_date.isoformat(),
        "chars": len(body),
    }
