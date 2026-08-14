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
from app.memory import ingest as memory_ingest
from app.memory.embeddings import memory_enabled

DIGEST_MAX_CHARS = 1000

# SMS teaser budget: 300 GSM-7 chars = 2 concatenated segments (2 x 153).
DIGEST_SMS_TEASER_MAX_CHARS = 300

SEND_DIGEST_SCHEMA = {
    "name": "send_digest",
    "description": (
        "Deliver the finished morning digest to the user. Call this exactly once "
        "to finish. The body must be <= 1000 characters of plain text (no "
        "markdown), starting with a 'PORTFOLIO:' line, containing a 'TOP RISK' "
        "section, and ending with a 'WATCH TODAY:' line. If it is too long or "
        "malformed you will be asked to fix it and try again. For a Pro digest, "
        "also pass 'holdings': the per-holding breakdown (plain text, no "
        "'HOLDINGS' label); it is shown on longer channels (email/Discord/web) "
        "while text-message users receive a short teaser (portfolio line, top "
        "risk, and a link to the full digest)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "body": {"type": "string"},
            "holdings": {"type": "string"},
        },
        "required": ["body"],
    },
}


def _today(tz: str) -> Any:
    return datetime.now(ZoneInfo(tz)).date()


# Punctuation the model likes that falls outside GSM-7. One such character
# flips the whole SMS to UCS-2 (67-char segments), tripling segment count,
# so normalize to ASCII before budgeting.
_GSM7_UNSAFE = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "…": "...",
        " ": " ",
        "→": "->",
        "•": "-",
    }
)


def _shorten(line: str, limit: int) -> str:
    if len(line) <= limit:
        return line
    return line[: max(limit - 3, 0)].rstrip() + "..."


def _digest_link(settings: Any) -> str:
    base = (settings.public_base_url or "https://cirvia.ca").rstrip("/")
    return f"{base}/app/dashboard#tab-digest"


def build_sms_teaser(body: str, *, link: str) -> str:
    """Derive the <=300-char SMS teaser from a validated digest body.

    Deterministic on purpose: validate_digest_structure already guarantees the
    PORTFOLIO: first line and the standalone TOP RISK label, so no extra model
    call (or its length-retry loop) is needed, and the segment budget is a hard
    guarantee. When the risk line can't be found the teaser degrades to the
    portfolio line + link; the link is never truncated.
    """
    lines = [ln.strip() for ln in body.translate(_GSM7_UNSAFE).strip().splitlines()]
    nonempty = [ln for ln in lines if ln]

    portfolio = nonempty[0] if nonempty else ""

    risk = ""
    for i, ln in enumerate(nonempty):
        if ln == "TOP RISK" or ln.startswith("TOP RISK:"):
            risk = ln.removeprefix("TOP RISK").lstrip(":").strip()
            if not risk:
                for nxt in nonempty[i + 1 :]:
                    # Stop at the next section label instead of pulling its
                    # heading (or the watch line) in as the "risk".
                    if nxt.startswith("WATCH TODAY:") or (
                        nxt == nxt.upper() and any(c.isalpha() for c in nxt)
                    ):
                        break
                    risk = nxt
                    break
            break

    tail = f"Full digest: {link}"
    budget = DIGEST_SMS_TEASER_MAX_CHARS - len(tail) - 1  # newline before tail

    parts: list[str] = []
    if portfolio:
        if risk:
            risk_line = f"TOP RISK: {risk}"
            # Risk gives way first; the portfolio line keeps at least half.
            portfolio = _shorten(portfolio, max(budget // 2, budget - len(risk_line) - 1))
            risk_line = _shorten(risk_line, budget - len(portfolio) - 1)
            parts = [portfolio, risk_line] if len(risk_line) > len("TOP RISK: ") else [portfolio]
        else:
            parts = [_shorten(portfolio, budget)]
    parts.append(tail)
    return "\n".join(parts)


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

    # Optional Pro-only per-holding breakdown. The rich body (core + HOLDINGS)
    # is stored and sent to longer channels; SMS gets a derived teaser.
    holdings = payload.get("holdings")
    rich_body = body
    if isinstance(holdings, str) and holdings.strip():
        holdings = holdings.strip()
        if len(holdings) > settings.digest_holdings_max_chars:
            raise ValueError(
                f"holdings section is {len(holdings)} chars; must be <= "
                f"{settings.digest_holdings_max_chars}. Shorten it (drop quiet "
                "detail or tighten sentences) and call send_digest again."
            )
        rich_body = f"{body}\n\nHOLDINGS\n{holdings}"

    # Deterministic watched-tickers section built by the digest pipeline; long
    # channels only — SMS gets only the teaser.
    watchlist_section = getattr(ctx, "watchlist_section", None)
    if isinstance(watchlist_section, str) and watchlist_section.strip():
        rich_body = f"{rich_body}\n\nWATCHLIST\n{watchlist_section.strip()}"

    tz = getattr(ctx, "timezone", None) or settings.tz
    digest_date = _today(tz)
    run_id = getattr(ctx, "run_id", None)
    user_id = getattr(ctx, "user_id", None)

    # Store the rich body so the dashboard and /digest/latest show the full
    # breakdown; the SMS channel gets the teaser via `sms_body`.
    digest_id = await ctx.repo.upsert_digest(
        run_id=run_id, body=rich_body, digest_date=digest_date, user_id=user_id
    )

    # Fire-and-forget semantic-memory ingestion (fail-open; no-op without a
    # VOYAGE_API_KEY). The digest must never fail because embedding did.
    if digest_id is not None and memory_enabled(settings):
        async def _embed() -> None:
            positions = await ctx.repo.list_positions(user_id=user_id)
            await memory_ingest.embed_digest(
                ctx.repo,
                user_id=user_id,
                digest_id=digest_id,
                body=rich_body,
                digest_date=digest_date,
                holdings_tickers=sorted({p.ticker for p in positions}),
            )

        memory_ingest.schedule(_embed())

    await ctx.repo.enqueue_outbound(
        rich_body,
        user_id=user_id,
        kind="digest",
        subject=f"Your morning digest, {digest_date.strftime('%b %d')}",
        sms_body=build_sms_teaser(body, link=_digest_link(settings)),
        push=True,
        push_title="Your morning digest",
        deep_link="cirvia://digest",
    )

    return {
        "status": "sent",
        "digest_date": digest_date.isoformat(),
        "chars": len(rich_body),
    }
