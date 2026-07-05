"""Morning digest orchestrator: plan -> investigate -> synthesize + send.

All three stages are anchored to a single ``agent_runs`` row (trigger='digest')
that owns the resulting ``digests`` row. Stage 2 investigations run as their own
``run_agent`` sub-loops (chat toolset, small budgets). On any failure the user
still receives a fallback digest — silent failure is unacceptable.

Scheduled delivery uses ``run_digests_for_all``: fan-out per user with plan
cadence (Free weekly Mon / Pro daily weekdays), monthly cost caps, and
``(user_id, digest_date)`` idempotency.
"""

from __future__ import annotations

import json
import time
import traceback
import uuid
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.agent import planner, synthesizer
from app.agent.budget import Budget
from app.agent.loop import run_agent
from app.agent.prompts import CHAT_SYSTEM_PROMPT, PROMPT_VERSION
from app.auth.context import set_current_user_id
from app.config import DEFAULT_USER_ID, Settings, get_settings, monthly_cost_cap
from app.db.repo import Repo
from app.observability.logging import Observer
from app.plans import digest_cadence_due, max_digest_holdings
from app.tools import market, news, portfolio
from app.tools.registry import CHAT_TOOLS, ToolContext

FALLBACK_BODY = "Digest failed this morning — check /runs for details."

_OWNER_USER_ID = uuid.UUID(DEFAULT_USER_ID)


def _get_client(client: Any) -> Any:
    if client is not None:
        return client
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=get_settings().anthropic_api_key)


def _user_plan_and_tz(
    user: Any | None, *, user_id: uuid.UUID, settings: Settings
) -> tuple[str, str]:
    if user_id == _OWNER_USER_ID and user is None:
        return "pro", settings.tz
    if user is None:
        return "free", settings.tz
    return getattr(user, "plan", "free"), getattr(user, "timezone", settings.tz)


def _trim_positions(
    positions: list[dict[str, Any]], cap: int | None
) -> list[dict[str, Any]]:
    if cap is None or len(positions) <= cap:
        return positions
    # Largest market value first; unpriced rows sort last.
    def _mv(p: dict[str, Any]) -> float:
        mv = p.get("market_value")
        return float(mv) if mv is not None else -1.0

    return sorted(positions, key=_mv, reverse=True)[:cap]


async def build_market_context(
    ctx: ToolContext,
    *,
    tz: str,
    max_holdings: int | None = None,
) -> str:
    """Assemble positions + day/week moves + yesterday's digest + today's date."""
    today = datetime.now(ZoneInfo(tz)).date()
    yesterday = today - timedelta(days=1)

    pf = await portfolio.get_portfolio({}, ctx)
    positions = _trim_positions(pf.get("positions", []), max_holdings)

    week_moves: dict[str, Any] = {}
    for pos in positions:
        ticker = pos["ticker"]
        try:
            hist = await market.get_price_history({"ticker": ticker, "days": 7}, ctx)
            week_moves[ticker] = hist.get("period_return_pct")
        except Exception:  # noqa: BLE001 - best effort
            week_moves[ticker] = None

    yesterday_digest = await ctx.repo.get_digest(
        yesterday, user_id=getattr(ctx, "user_id", None)
    )

    context = {
        "today": today.isoformat(),
        "positions": positions,
        "totals": pf.get("totals", {}),
        "week_return_pct_by_ticker": week_moves,
        "yesterday_digest": yesterday_digest.body if yesterday_digest else None,
    }
    if max_holdings is not None and len(pf.get("positions", [])) > max_holdings:
        context["holdings_capped"] = max_holdings
    return json.dumps(context, default=str)


def _findings_text(results: list[dict[str, str]], market_context: str) -> str:
    lines = ["MARKET CONTEXT:", market_context, "", "INVESTIGATION FINDINGS:"]
    for r in results:
        lines.append(f"\nQ: {r['question']}\nFinding: {r['answer']}")
    return "\n".join(lines)


async def run_digest_pipeline(
    db: Repo,
    *,
    user_id: uuid.UUID | None = None,
    client: Any = None,
    force: bool = False,
) -> dict[str, Any]:
    settings = get_settings()
    uid = user_id or _OWNER_USER_ID
    user = await db.get_user(uid)
    plan, tz = _user_plan_and_tz(user, user_id=uid, settings=settings)
    local_today = datetime.now(ZoneInfo(tz)).date()

    if not force:
        if not digest_cadence_due(plan, local_today):
            return {
                "user_id": str(uid),
                "status": "skipped_cadence",
                "plan": plan,
            }
        if await db.get_digest(local_today, user_id=uid) is not None:
            return {"user_id": str(uid), "status": "skipped_exists", "plan": plan}
        if uid != _OWNER_USER_ID and await db.monthly_cost_usd(uid) >= monthly_cost_cap(
            plan, settings
        ):
            return {"user_id": str(uid), "status": "skipped_cost_cap", "plan": plan}

    positions = await db.list_positions(user_id=uid)
    if not positions:
        return {"user_id": str(uid), "status": "skipped_no_positions", "plan": plan}

    set_current_user_id(uid)
    client = _get_client(client)
    holdings_cap = max_digest_holdings(plan, settings)
    ctx = ToolContext(
        settings=settings,
        repo=db,
        user_id=uid,
        timezone=tz,
        enqueue_delivery=settings.imessage_recipient != "",
    )

    started = time.monotonic()
    anchor_run_id = await db.create_run(
        trigger="digest",
        user_message="[morning digest]",
        model=settings.model,
        prompt_version=PROMPT_VERSION,
        user_id=uid,
    )
    ctx.run_id = anchor_run_id
    observer = Observer(db, anchor_run_id)
    budget = Budget(
        max_iterations=settings.digest_max_iterations,
        max_cost_usd=settings.digest_max_cost_usd,
        model=settings.model,
    )

    try:
        market_context = await build_market_context(
            ctx, tz=tz, max_holdings=holdings_cap
        )

        investigations = await planner.plan(
            client=client,
            model=settings.model,
            observer=observer,
            budget=budget,
            market_context=market_context,
        )

        tickers = [
            p["ticker"] for p in json.loads(market_context).get("positions", [])
        ]
        await news.prefetch_news_for_tickers(tickers)

        results: list[dict[str, str]] = []
        for inv in investigations:
            sub_budget = Budget(max_iterations=5, max_cost_usd=0.30, model=settings.model)
            sub = await run_agent(
                inv["question"],
                trigger="digest",
                system_prompt=CHAT_SYSTEM_PROMPT,
                tools=CHAT_TOOLS,
                budget=sub_budget,
                db=db,
                client=client,
                user_id=uid,
            )
            results.append({"question": inv["question"], "answer": sub.answer})

        body = await synthesizer.synthesize_and_send(
            client=client,
            model=settings.model,
            observer=observer,
            budget=budget,
            ctx=ctx,
            findings_text=_findings_text(results, market_context),
            iteration_start=2,
        )

        await db.finalize_run(
            anchor_run_id,
            status="completed",
            final_answer=body,
            iterations=budget.iterations,
            input_tokens=budget.input_tokens,
            output_tokens=budget.output_tokens,
            cost_usd=budget.cost_usd,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        return {
            "run_id": str(anchor_run_id),
            "user_id": str(uid),
            "status": "completed",
            "plan": plan,
            "body": body,
        }

    except Exception:
        await _deliver_fallback(db, ctx, anchor_run_id, tz=tz)
        await db.finalize_run(
            anchor_run_id,
            status="error",
            final_answer=FALLBACK_BODY,
            iterations=budget.iterations,
            input_tokens=budget.input_tokens,
            output_tokens=budget.output_tokens,
            cost_usd=budget.cost_usd,
            latency_ms=int((time.monotonic() - started) * 1000),
            error_detail=traceback.format_exc(),
        )
        return {
            "run_id": str(anchor_run_id),
            "user_id": str(uid),
            "status": "error",
            "plan": plan,
            "body": FALLBACK_BODY,
        }
    finally:
        set_current_user_id(None)


async def run_digests_for_all(db: Repo, *, client: Any = None) -> list[dict[str, Any]]:
    """Scheduled entry point: one digest per eligible user under cadence + caps."""
    recipients = await db.list_digest_recipients()
    results: list[dict[str, Any]] = []
    for uid in recipients:
        try:
            results.append(await run_digest_pipeline(db, user_id=uid, client=client))
        except Exception:
            results.append(
                {"user_id": str(uid), "status": "error", "body": FALLBACK_BODY}
            )
    return results


async def _deliver_fallback(
    db: Repo, ctx: ToolContext, anchor_run_id: Any, *, tz: str
) -> None:
    today = datetime.now(ZoneInfo(tz)).date()
    try:
        await db.upsert_digest(
            run_id=anchor_run_id,
            body=FALLBACK_BODY,
            digest_date=today,
            user_id=getattr(ctx, "user_id", None),
        )
        if ctx.enqueue_delivery:
            await db.enqueue_outbound(
                FALLBACK_BODY, user_id=getattr(ctx, "user_id", None)
            )
    except Exception:  # noqa: BLE001 - fallback delivery is best-effort
        pass
