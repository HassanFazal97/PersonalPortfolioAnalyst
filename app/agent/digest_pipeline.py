"""Morning digest orchestrator: plan -> investigate -> synthesize + send.

All three stages are anchored to a single ``agent_runs`` row (trigger='digest')
that owns the resulting ``digests`` row. Stage 2 investigations run as their own
``run_agent`` sub-loops (chat toolset, small budgets). On any failure the user
still receives a fallback digest — silent failure is unacceptable.
"""

from __future__ import annotations

import json
import time
import traceback
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.agent import planner, synthesizer
from app.agent.budget import Budget
from app.agent.loop import run_agent
from app.agent.prompts import CHAT_SYSTEM_PROMPT, PROMPT_VERSION
from app.config import get_settings
from app.db.repo import Repo
from app.observability.logging import Observer
from app.tools import market, portfolio
from app.tools.registry import CHAT_TOOLS, ToolContext

FALLBACK_BODY = "Digest failed this morning — check /runs for details."


def _get_client(client: Any) -> Any:
    if client is not None:
        return client
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=get_settings().anthropic_api_key)


async def build_market_context(ctx: ToolContext, *, tz: str) -> str:
    """Assemble positions + day/week moves + yesterday's digest + today's date."""
    today = datetime.now(ZoneInfo(tz)).date()
    yesterday = today - timedelta(days=1)

    pf = await portfolio.get_portfolio({}, ctx)

    week_moves: dict[str, Any] = {}
    for pos in pf.get("positions", []):
        ticker = pos["ticker"]
        try:
            hist = await market.get_price_history({"ticker": ticker, "days": 7}, ctx)
            week_moves[ticker] = hist.get("period_return_pct")
        except Exception:  # noqa: BLE001 - best effort
            week_moves[ticker] = None

    yesterday_digest = await ctx.repo.get_digest(yesterday)

    context = {
        "today": today.isoformat(),
        "positions": pf.get("positions", []),
        "totals": pf.get("totals", {}),
        "week_return_pct_by_ticker": week_moves,
        "yesterday_digest": yesterday_digest.body if yesterday_digest else None,
    }
    return json.dumps(context, default=str)


def _findings_text(results: list[dict[str, str]], market_context: str) -> str:
    lines = ["MARKET CONTEXT:", market_context, "", "INVESTIGATION FINDINGS:"]
    for r in results:
        lines.append(f"\nQ: {r['question']}\nFinding: {r['answer']}")
    return "\n".join(lines)


async def run_digest_pipeline(db: Repo, *, client: Any = None) -> dict[str, Any]:
    settings = get_settings()
    client = _get_client(client)
    ctx = ToolContext(settings=settings, repo=db, enqueue_delivery=settings.imessage_recipient != "")

    started = time.monotonic()
    anchor_run_id = await db.create_run(
        trigger="digest",
        user_message="[morning digest]",
        model=settings.model,
        prompt_version=PROMPT_VERSION,
    )
    ctx.run_id = anchor_run_id
    observer = Observer(db, anchor_run_id)
    budget = Budget(
        max_iterations=settings.digest_max_iterations,
        max_cost_usd=settings.digest_max_cost_usd,
        model=settings.model,
    )

    try:
        market_context = await build_market_context(ctx, tz=settings.tz)

        # Stage 1 — plan (iterations 1–2 on the anchor run).
        investigations = await planner.plan(
            client=client,
            model=settings.model,
            observer=observer,
            budget=budget,
            market_context=market_context,
        )

        # Stage 2 — investigate (separate sub-runs, chat toolset, small budget).
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
            )
            results.append({"question": inv["question"], "answer": sub.answer})

        # Stage 3 — synthesize + send (anchor run, send_digest only).
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
        return {"run_id": str(anchor_run_id), "status": "completed", "body": body}

    except Exception:
        # Never fail silently: deliver a fallback digest and record the error.
        await _deliver_fallback(db, ctx, anchor_run_id)
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
        return {"run_id": str(anchor_run_id), "status": "error", "body": FALLBACK_BODY}


async def _deliver_fallback(db: Repo, ctx: ToolContext, anchor_run_id) -> None:
    today = datetime.now(ZoneInfo(get_settings().tz)).date()
    try:
        await db.upsert_digest(run_id=anchor_run_id, body=FALLBACK_BODY, digest_date=today)
        if ctx.enqueue_delivery:
            await db.enqueue_outbound(FALLBACK_BODY)
    except Exception:  # noqa: BLE001 - fallback delivery is best-effort
        pass
