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
from app.plans import (
    digest_cadence_due,
    max_digest_holdings,
    trial_decision_pending,
    user_plan_and_tz,
)
from app.tools import market, news, portfolio
from app.tools.registry import CHAT_TOOLS, ToolContext

FALLBACK_BODY = "Digest failed this morning — check /runs for details."

_OWNER_USER_ID = uuid.UUID(DEFAULT_USER_ID)


def _get_client(client: Any) -> Any:
    if client is not None:
        return client
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=get_settings().anthropic_api_key)


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


def resolve_digest_positions(
    all_positions: list[dict[str, Any]],
    *,
    plan: str,
    settings: Settings,
    digest_tickers: list[str],
) -> list[dict[str, Any]]:
    """Pick which holdings feed the digest for this user/plan."""
    cap = max_digest_holdings(plan, settings)
    if cap is None:
        return all_positions
    if digest_tickers:
        by_ticker = {p["ticker"]: p for p in all_positions}
        picked = [by_ticker[t] for t in digest_tickers if t in by_ticker]
        if picked:
            return picked[:cap]
    return _trim_positions(all_positions, cap)


async def build_market_context(
    ctx: ToolContext,
    *,
    tz: str,
    plan: str,
    digest_tickers: list[str],
) -> str:
    """Assemble positions + day/week moves + yesterday's digest + today's date."""
    today = datetime.now(ZoneInfo(tz)).date()
    yesterday = today - timedelta(days=1)
    settings = ctx.settings

    pf = await portfolio.get_portfolio({}, ctx)
    all_positions = pf.get("positions", [])
    positions = resolve_digest_positions(
        all_positions,
        plan=plan,
        settings=settings,
        digest_tickers=digest_tickers,
    )
    cap = max_digest_holdings(plan, settings)

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
    if cap is not None and len(all_positions) > cap:
        context["holdings_capped"] = cap
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
    plan, tz = user_plan_and_tz(user, user_id=uid, settings=settings)
    local_today = datetime.now(ZoneInfo(tz)).date()

    if not force:
        # A lapsed trial pauses digests entirely (neither cadence) until the
        # user logs in and picks paid Pro or Free.
        if trial_decision_pending(user):
            return {
                "user_id": str(uid),
                "status": "skipped_trial_decision",
                "plan": plan,
            }
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
    ctx = ToolContext(
        settings=settings,
        repo=db,
        user_id=uid,
        timezone=tz,
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
        digest_tickers = await db.get_digest_tickers(uid)
        market_context = await build_market_context(
            ctx, tz=tz, plan=plan, digest_tickers=digest_tickers
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
        await _persist_prefetched_news(
            db, uid, anchor_run_id, tickers, client=client, budget=budget
        )

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


async def _persist_prefetched_news(
    db: Repo,
    user_id: uuid.UUID,
    run_id: uuid.UUID,
    tickers: list[str],
    *,
    client: Any = None,
    budget: Budget | None = None,
) -> None:
    """Store the important prefetched articles for the dashboard feed.

    Usually a no-op: the daily news_refresh job persisted the same articles
    earlier (fingerprint dedup). Kept so news still flows on digest days when
    NEWS_REFRESH_CRON is disabled."""
    from app.agent.news_refresh import persist_important_news

    await persist_important_news(
        db, user_id, tickers, client=client, run_id=run_id, budget=budget
    )


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
        await db.enqueue_outbound(
            FALLBACK_BODY,
            user_id=getattr(ctx, "user_id", None),
            kind="digest",
            subject="Your morning digest",
        )
    except Exception:  # noqa: BLE001 - fallback delivery is best-effort
        pass
