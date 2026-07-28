"""Best Stocks pipeline: screen -> per-pick analysts -> verify -> synthesize.

Runs once globally per day (the output is market data, not user data), under
the owner service context, and persists one ``stock_picks_runs`` row every
Pro user's dashboard reads. All stages hang off one anchor ``agent_runs`` row
(trigger='stock_picks') whose budget accumulates every sub-loop, so the
anchor reports the run's true total cost and the Observer trail makes any
pick auditable end to end.

Accuracy posture (why the stages look the way they do):
- Stage A is pure math over stored data — every ranking number is computed
  in Python, never by a model. A stale store aborts the run rather than
  analyzing garbage.
- Stage B analysts may only cite their fact sheet or a tool result from
  their own sub-run; their JSON is machine-checked afterwards.
- Stage C is two-tier: a deterministic evidence check (drops/repairs any
  number that drifts from the fact sheet) and an adversarial critic that
  re-checks free-text claims with its own tools. Picks with 2+ challenged
  claims are demoted below every clean pick.
- Confidence is computed here, not asked of the model.

Failure philosophy mirrors the deep dive: a dead analyst degrades that pick
to quant-only, a dead critic leaves claims 'unverified', and only a stale
data store or an infrastructure failure produces an 'error' run.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import traceback
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.agent.budget import Budget
from app.agent.loop import call_and_log, run_agent
from app.agent.picks.analysts import (
    ANALYST_CONCURRENCY,
    BUDGET_ADMISSION_CUTOFF,
    CONFIDENCE_GAP_CAP,
    CONFIDENCE_WEIGHTS,
    MODEL_CONFIDENCE_MAP,
    MOVER_MAX_TOKENS,
    MOVER_NEWS_LOOKBACK_DAYS,
    MOVER_NEWS_MAX_RESULTS,
    MOVER_TIMEOUT_SECONDS,
    PICK_ANALYST_MAX_COST_USD,
    PICK_ANALYST_MAX_ITERATIONS,
    PICK_ANALYST_TIMEOUT_SECONDS,
    PICK_ANALYST_TOOLS,
    PICKS_CRITIC_MAX_COST_USD,
    PICKS_CRITIC_MAX_ITERATIONS,
    PICKS_CRITIC_TIMEOUT_SECONDS,
    PICKS_CRITIC_TOOLS,
)
from app.agent.picks.verify import verify_evidence
from app.agent.prompts import (
    PICKS_ANALYST_PROMPT,
    PICKS_CRITIC_PROMPT,
    PICKS_MOVER_PROMPT,
    PICKS_SYNTHESIS_PROMPT,
    PICKS_SYNTHESIS_RETRY_SUFFIX,
    PROMPT_VERSION,
)
from app.auth.context import set_current_user_id
from app.config import DEFAULT_USER_ID, get_settings
from app.observability.logging import Observer
from app.quant import screener
from app.tools import news
from app.tools.registry import ToolContext
from app.tools.universe import UNIVERSE_NAME, get_universe, universe_snapshot

logger = logging.getLogger(__name__)

METHODOLOGY_VERSION = 1
DISCLAIMER = (
    "Ranked by a quantitative model over public data. Informational only — "
    "not a recommendation to buy or sell. Do your own research."
)
# Below this fraction of the universe passing the eligibility gates, the data
# store is presumed stale (sync failure) and the run refuses to rank.
MIN_ELIGIBLE_FRACTION = 0.6
# A pick with this many challenged critic checks sorts below every clean pick.
DEMOTION_CHALLENGED_COUNT = 2

_OWNER_USER_ID = uuid.UUID(DEFAULT_USER_ID)


def _get_client(client: Any) -> Any:
    if client is not None:
        return client
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=get_settings().anthropic_api_key)


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def _join_text(content: list[dict[str, Any]]) -> str:
    return "\n".join(
        b.get("text", "") for b in content if b.get("type") == "text"
    ).strip()


def _loads_lenient(text: str) -> Any:
    """json.loads with a fallback that extracts the first balanced {...}
    block — models occasionally preface their JSON with a sentence despite
    the strict-JSON instruction, and a whole analysis shouldn't degrade to
    quant-only over a prose prefix."""
    stripped = _strip_fences(text)
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        pass
    start = stripped.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(stripped)):
        ch = stripped[i]
        if escape:
            escape = False
        elif ch == "\\":
            escape = in_str
        elif ch == '"':
            in_str = not in_str
        elif not in_str:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(stripped[start : i + 1])
                    except json.JSONDecodeError:
                        return None
    return None


def parse_analysis(text: str) -> dict[str, Any] | None:
    """Analyst output -> analysis dict, or None if unusable."""
    data = _loads_lenient(text)
    if not isinstance(data, dict) or not data.get("thesis"):
        return None
    return data


def parse_checks(text: str) -> list[dict[str, str]]:
    """Critic output -> normalized checks. Tolerant: garbage -> []."""
    data = _loads_lenient(text)
    checks = data.get("checks") if isinstance(data, dict) else None
    if not isinstance(checks, list):
        return []
    cleaned = []
    for c in checks:
        if isinstance(c, dict) and c.get("claim"):
            verdict = c.get("verdict")
            cleaned.append(
                {
                    "ticker": str(c.get("ticker", "")).upper(),
                    "claim": str(c["claim"]),
                    "verdict": verdict
                    if verdict in ("verified", "challenged")
                    else "unverified",
                    "note": str(c.get("note", "")),
                }
            )
    return cleaned


def parse_overview(text: str) -> dict[str, str] | None:
    data = _loads_lenient(text)
    if not isinstance(data, dict) or not data.get("overview"):
        return None
    return {"headline": str(data.get("headline", "")), "overview": str(data["overview"])}


def compute_confidence(
    *,
    rank: int,
    total_ranked: int,
    factors: dict[str, Any],
    verified: int,
    challenged: int,
    model_confidence: str | None,
    has_gaps: bool,
) -> float:
    """Calibrated pick confidence, computed in Python — never model-asserted."""
    pct = 1.0 - (rank - 1) / max(total_ranked, 1)
    coverage = sum(1 for v in factors.values() if v is not None) / max(len(factors), 1)
    checked = verified + challenged
    verification = verified / checked if checked else 0.5
    model_c = MODEL_CONFIDENCE_MAP.get(model_confidence or "", 0.3)
    w = CONFIDENCE_WEIGHTS
    score = (
        w["composite_percentile"] * pct
        + w["factor_coverage"] * coverage
        + w["verification"] * verification
        + w["model_confidence"] * model_c
    )
    if has_gaps:
        score = min(score, CONFIDENCE_GAP_CAP)
    return round(score, 3)


def _fact_sheet_message(row: dict[str, Any], as_of: str) -> str:
    sheet = {
        "as_of": as_of,
        "ticker": row["ticker"],
        "name": row.get("name"),
        "sector": row.get("sector"),
        "last_price": row.get("last_price"),
        "screen_rank": row.get("rank"),
        "composite_score": row.get("composite"),
        "factor_scores": row.get("factors"),
        "metrics": (row.get("evidence") or {}).get("metrics"),
        "price_and_analyst": {
            k: v
            for k, v in (row.get("evidence") or {}).items()
            if k != "metrics"
        },
    }
    return (
        "FACT SHEET (your ground truth for this candidate):\n"
        + json.dumps(sheet)
        + "\n\nWrite the analysis for this candidate."
    )


async def _run_analyst(
    db: Any,
    row: dict[str, Any],
    *,
    as_of: str,
    client: Any,
    settings: Any,
    anchor_budget: Budget,
) -> dict[str, Any] | None:
    """One per-pick analyst sub-loop. None on failure — never raises."""
    sub_budget = Budget(
        max_iterations=PICK_ANALYST_MAX_ITERATIONS,
        max_cost_usd=PICK_ANALYST_MAX_COST_USD,
        model=settings.model,
    )
    try:
        sub = await asyncio.wait_for(
            run_agent(
                _fact_sheet_message(row, as_of),
                trigger="stock_picks",
                system_prompt=PICKS_ANALYST_PROMPT,
                tools=PICK_ANALYST_TOOLS,
                budget=sub_budget,
                db=db,
                client=client,
                user_id=_OWNER_USER_ID,
                # A full analysis JSON (thesis + evidence + risks) regularly
                # runs past the loop's 1024 default; truncated JSON can't parse.
                max_tokens=2048,
            ),
            timeout=PICK_ANALYST_TIMEOUT_SECONDS,
        )
        analysis = parse_analysis(sub.answer or "")
        if analysis is None:
            # One retry inside the same sub-loop budget is not possible via
            # run_agent; a malformed answer degrades to quant-only.
            logger.warning("pick analyst returned unparseable JSON for %s", row["ticker"])
        return analysis
    except Exception:  # noqa: BLE001 - a dead analyst degrades, not aborts
        logger.warning("pick analyst failed for %s", row["ticker"], exc_info=True)
        return None
    finally:
        anchor_budget.record_usage(sub_budget.input_tokens, sub_budget.output_tokens)


async def _explain_mover(
    mover: dict[str, Any],
    *,
    ctx: ToolContext,
    client: Any,
    settings: Any,
    observer: Observer,
    anchor_budget: Budget,
) -> dict[str, Any]:
    """News-grounded 'why' for one mover: fetch news in Python, then one
    classifier-model call to narrate it (the anomaly-narration pattern).
    Never invents a catalyst: no news, or any failure -> not grounded."""
    fallback = {
        "why": "No clear catalyst in recent news.",
        "news_grounded": False,
        "sources": [],
    }
    try:
        found = await asyncio.wait_for(
            news.search_news(
                {
                    "query": mover["ticker"],
                    "lookback_days": MOVER_NEWS_LOOKBACK_DAYS,
                    "max_results": MOVER_NEWS_MAX_RESULTS,
                    "classify": False,
                },
                ctx,
            ),
            timeout=MOVER_TIMEOUT_SECONDS,
        )
        items = found.get("items") or []
        if not items:
            return {**mover, **fallback}
        mover_budget = Budget(
            max_iterations=1, max_cost_usd=0.05, model=settings.classifier_model
        )
        content, _ = await asyncio.wait_for(
            call_and_log(
                client,
                model=settings.classifier_model,
                system_prompt=PICKS_MOVER_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"mover": mover, "news": items}, default=str
                        ),
                    }
                ],
                tools=None,
                observer=observer,
                iteration=anchor_budget.iterations + 1,
                budget=mover_budget,
                max_tokens=MOVER_MAX_TOKENS,
            ),
            timeout=MOVER_TIMEOUT_SECONDS,
        )
        anchor_budget.input_tokens += mover_budget.input_tokens
        anchor_budget.output_tokens += mover_budget.output_tokens
        anchor_budget.record_flat_cost(mover_budget.cost_usd)
        parsed = _loads_lenient(_join_text(content))
        if not isinstance(parsed, dict) or not parsed.get("why"):
            return {**mover, **fallback}
        grounded = bool(parsed.get("news_grounded"))
        return {
            **mover,
            "why": str(parsed["why"]),
            "news_grounded": grounded,
            "sources": [str(s) for s in parsed.get("sources") or []] if grounded else [],
        }
    except Exception:  # noqa: BLE001 - an unexplained mover is still a mover
        logger.warning("mover explanation failed for %s", mover["ticker"], exc_info=True)
        return {**mover, **fallback}


async def _run_critic(
    db: Any,
    picks: list[dict[str, Any]],
    *,
    client: Any,
    settings: Any,
    anchor_budget: Budget,
) -> list[dict[str, str]] | None:
    """Adversarial verification over all draft analyses. None = critic itself
    failed (claims stay 'unverified'); [] = nothing worth checking."""
    drafts = [
        {
            "ticker": p["ticker"],
            "thesis": p.get("thesis"),
            "why_now": p.get("why_now"),
            "risks": p.get("risks"),
            "catalysts": p.get("catalysts"),
        }
        for p in picks
        if p.get("analysis") == "ok"
    ]
    if not drafts:
        return []
    sub_budget = Budget(
        max_iterations=PICKS_CRITIC_MAX_ITERATIONS,
        max_cost_usd=PICKS_CRITIC_MAX_COST_USD,
        model=settings.model,
    )
    try:
        sub = await asyncio.wait_for(
            run_agent(
                "DRAFT PICK ANALYSES TO VERIFY:\n\n" + json.dumps(drafts),
                trigger="stock_picks",
                system_prompt=PICKS_CRITIC_PROMPT,
                tools=PICKS_CRITIC_TOOLS,
                budget=sub_budget,
                db=db,
                client=client,
                user_id=_OWNER_USER_ID,
                max_tokens=2048,  # up to 10 checks with notes truncates at 1024
            ),
            timeout=PICKS_CRITIC_TIMEOUT_SECONDS,
        )
        return parse_checks(sub.answer or "")
    except Exception:  # noqa: BLE001
        logger.warning("picks critic failed", exc_info=True)
        return None
    finally:
        anchor_budget.record_usage(sub_budget.input_tokens, sub_budget.output_tokens)


async def _synthesize_overview(
    client: Any,
    settings: Any,
    observer: Observer,
    budget: Budget,
    payload: dict[str, Any],
) -> dict[str, str]:
    blob = json.dumps(
        {
            "picks": [
                {
                    "ticker": p["ticker"],
                    "sector": p.get("sector"),
                    "composite": p.get("composite"),
                    "thesis": p.get("thesis"),
                }
                for p in payload["picks"]
            ],
            "movers": payload["movers"],
        }
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": blob}]
    content, _ = await call_and_log(
        client,
        model=settings.model,
        system_prompt=PICKS_SYNTHESIS_PROMPT,
        messages=messages,
        tools=None,
        observer=observer,
        iteration=budget.iterations + 1,
        budget=budget,
        max_tokens=1500,
    )
    parsed = parse_overview(_join_text(content))
    if parsed is not None:
        return parsed
    messages.append({"role": "assistant", "content": content})
    messages.append({"role": "user", "content": PICKS_SYNTHESIS_RETRY_SUFFIX})
    content, _ = await call_and_log(
        client,
        model=settings.model,
        system_prompt=PICKS_SYNTHESIS_PROMPT,
        messages=messages,
        tools=None,
        observer=observer,
        iteration=budget.iterations + 1,
        budget=budget,
        max_tokens=1500,
    )
    return parse_overview(_join_text(content)) or {"headline": "", "overview": ""}


async def run_stock_picks(
    db: Any,
    *,
    client: Any = None,
    run_date: date | None = None,
) -> dict[str, Any]:
    """Execute the daily pipeline. Returns ``{picks_run_id, status, cost_usd}``."""
    settings = get_settings()
    set_current_user_id(_OWNER_USER_ID)
    client = _get_client(client)
    run_date = run_date or date.today()
    started = time.monotonic()

    run_id = await db.create_run(
        trigger="stock_picks",
        user_message="[best stocks daily run]",
        model=settings.model,
        prompt_version=PROMPT_VERSION,
        user_id=_OWNER_USER_ID,
    )
    picks_run_id = await db.create_picks_run(
        run_date=run_date,
        universe=UNIVERSE_NAME,
        run_id=run_id,
        methodology_version=METHODOLOGY_VERSION,
    )
    observer = Observer(db, run_id)
    budget = Budget(
        max_iterations=settings.picks_max_iterations,
        max_cost_usd=settings.picks_max_cost_usd,
        model=settings.model,
    )
    ctx = ToolContext(settings=settings, repo=db, user_id=_OWNER_USER_ID)
    ctx.run_id = run_id
    ctx.client = client
    ctx.budget = budget

    async def finalize(
        status: str,
        payload: dict | None,
        stats: dict | None,
        error: str | None = None,
    ) -> dict[str, Any]:
        await db.update_picks_run(
            picks_run_id,
            status=status,
            payload=payload,
            stats=stats,
            cost_usd=budget.cost_usd,
        )
        await db.finalize_run(
            run_id,
            status="completed" if status in ("completed", "partial") else "error",
            final_answer=(payload or {}).get("headline") or status,
            iterations=budget.iterations,
            input_tokens=budget.input_tokens,
            output_tokens=budget.output_tokens,
            cost_usd=budget.cost_usd,
            latency_ms=int((time.monotonic() - started) * 1000),
            error_detail=error,
        )
        return {
            "picks_run_id": str(picks_run_id),
            "status": status,
            "cost_usd": round(budget.cost_usd, 4),
        }

    try:
        # ---- Stage A: pure-math screen over stored data ($0) --------------
        tickers = get_universe(settings.picks_universe_limit)
        fund_rows = await db.get_ticker_fundamentals(tickers)
        now = datetime.now(timezone.utc)
        fundamentals: dict[str, dict[str, Any]] = {}
        ages: dict[str, float] = {}
        for t, row in fund_rows.items():
            if row.fetch_error:
                continue
            fundamentals[t] = row.data
            ages[t] = (now - row.fetched_at).total_seconds() / 3600.0

        since = run_date - timedelta(days=settings.picks_history_days)
        price_rows = await db.get_daily_prices_bulk(tickers, since=since)
        closes = {
            t: [
                {"date": r.price_date.isoformat(), "adj_close": float(r.adj_close)}
                for r in rows
            ]
            for t, rows in price_rows.items()
        }

        screen = screener.score_universe(
            fundamentals,
            closes,
            as_of=run_date,
            fundamentals_age_hours=ages,
            max_movers=settings.picks_max_movers,
        )
        eligible_fraction = (
            screen.coverage.get("eligible", 0) / max(len(tickers), 1)
        )
        if eligible_fraction < MIN_ELIGIBLE_FRACTION:
            return await finalize(
                "error",
                None,
                {"coverage": screen.coverage, "note": "stale data"},
                error=(
                    f"only {screen.coverage.get('eligible', 0)}/{len(tickers)} "
                    "universe tickers passed the eligibility gates — data store "
                    "looks stale; refusing to rank"
                ),
            )

        candidates = screen.rows[: settings.picks_top_candidates]
        total_ranked = len(screen.rows)
        as_of_iso = run_date.isoformat()
        data_as_of = max(
            (c[-1]["date"] for c in closes.values() if c), default=as_of_iso
        )

        # ---- Stage B: per-pick analysts (bounded fan-out) ------------------
        sem = asyncio.Semaphore(ANALYST_CONCURRENCY)
        admission_cap = BUDGET_ADMISSION_CUTOFF * settings.picks_max_cost_usd
        skipped_for_budget: list[str] = []

        async def analyze(row: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
            async with sem:
                if budget.cost_usd >= admission_cap:
                    skipped_for_budget.append(row["ticker"])
                    return row["ticker"], None
                budget.start_iteration()
                return row["ticker"], await _run_analyst(
                    db, row, as_of=as_of_iso, client=client,
                    settings=settings, anchor_budget=budget,
                )

        analyses = dict(await asyncio.gather(*(analyze(r) for r in candidates)))

        # ---- Stage C1: deterministic evidence verification ------------------
        picks: list[dict[str, Any]] = []
        evidence_repaired = 0
        failed_analysts = 0
        for row in candidates:
            analysis = analyses.get(row["ticker"])
            pick: dict[str, Any] = {
                "ticker": row["ticker"],
                "name": row.get("name"),
                "sector": row.get("sector"),
                "rank": row["rank"],
                "last_price": row.get("last_price"),
                "composite": row.get("composite"),
                "factors": row.get("factors"),
                "evidence": row.get("evidence"),
            }
            if analysis is None:
                failed_analysts += 1
                pick["analysis"] = "unavailable"
                pick["valuation_evidence"] = []
                pick["data_gaps"] = ["analyst stage unavailable — quantitative scores only"]
            else:
                fact_metrics = (row.get("evidence") or {}).get("metrics") or {}
                verified_ev, notes = verify_evidence(
                    analysis.get("valuation_evidence"), fact_metrics
                )
                evidence_repaired += sum(1 for n in notes if n.startswith("repaired"))
                pick.update(
                    {
                        "analysis": "ok",
                        "thesis": str(analysis.get("thesis", "")),
                        "why_now": str(analysis.get("why_now", "")),
                        "valuation_evidence": verified_ev,
                        "evidence_notes": notes,
                        "risks": [
                            r for r in analysis.get("risks") or [] if isinstance(r, dict)
                        ],
                        "catalysts": [
                            str(c) for c in analysis.get("catalysts") or []
                        ],
                        "model_confidence": analysis.get("model_confidence"),
                        "data_gaps": [str(g) for g in analysis.get("data_gaps") or []],
                    }
                )
            picks.append(pick)

        # ---- Stage B2: movers-why -------------------------------------------
        movers = [
            await _explain_mover(
                m, ctx=ctx, client=client, settings=settings,
                observer=observer, anchor_budget=budget,
            )
            for m in screen.movers
        ]

        # ---- Stage C2: adversarial critic -----------------------------------
        checks: list[dict[str, str]] | None
        if budget.cost_usd >= admission_cap:
            checks = None
        else:
            budget.start_iteration()
            checks = await _run_critic(
                db, picks, client=client, settings=settings, anchor_budget=budget
            )
        checks_by_ticker: dict[str, list[dict[str, str]]] = {}
        for c in checks or []:
            checks_by_ticker.setdefault(c["ticker"], []).append(c)

        # ---- Stage D: confidence, demotion, synthesis, persist --------------
        for pick in picks:
            t_checks = checks_by_ticker.get(pick["ticker"], [])
            verified = sum(1 for c in t_checks if c["verdict"] == "verified")
            challenged = sum(1 for c in t_checks if c["verdict"] == "challenged")
            pick["verification"] = {
                "checked": len(t_checks),
                "verified": verified,
                "challenged": challenged,
                "checks": t_checks,
                "critic_ran": checks is not None,
            }
            pick["demoted"] = challenged >= DEMOTION_CHALLENGED_COUNT
            pick["confidence"] = compute_confidence(
                rank=pick["rank"],
                total_ranked=total_ranked,
                factors=pick.get("factors") or {},
                verified=verified,
                challenged=challenged,
                model_confidence=pick.get("model_confidence"),
                has_gaps=bool(pick.get("data_gaps")) or pick["analysis"] != "ok",
            )
        # Demoted picks sort below every clean pick; screen order within groups.
        picks.sort(key=lambda p: (p["demoted"], p["rank"]))
        picks = picks[: settings.picks_final_count]

        payload: dict[str, Any] = {
            "as_of": as_of_iso,
            "data_as_of": data_as_of,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "universe": universe_snapshot(settings.picks_universe_limit),
            "picks": picks,
            "movers": movers,
            "coverage": screen.coverage,
            "methodology_version": METHODOLOGY_VERSION,
            "disclaimer": DISCLAIMER,
        }
        verification_summary = {
            "checked": len(checks or []),
            "verified": sum(1 for c in checks or [] if c["verdict"] == "verified"),
            "challenged": sum(
                1 for c in checks or [] if c["verdict"] == "challenged"
            ),
            "evidence_repaired": evidence_repaired,
            "critic_ran": checks is not None,
        }
        payload["verification_summary"] = verification_summary

        try:
            overview = await asyncio.wait_for(
                _synthesize_overview(client, settings, observer, budget, payload),
                timeout=PICKS_CRITIC_TIMEOUT_SECONDS,
            )
        except Exception:  # noqa: BLE001 - picks stand without an overview
            logger.warning("picks synthesis failed", exc_info=True)
            overview = {"headline": "", "overview": ""}
        payload.update(overview)

        stats = {
            "coverage": screen.coverage,
            "verification": verification_summary,
            "failed_analysts": failed_analysts,
            "skipped_for_budget": skipped_for_budget,
            "movers": len(movers),
        }

        try:
            await db.insert_pick_entries(
                [
                    {
                        "picks_run_id": picks_run_id,
                        "run_date": run_date,
                        "ticker": p["ticker"],
                        "rank": p["rank"],
                        "composite_score": p.get("composite"),
                        "confidence": p.get("confidence"),
                        "entry_price": p.get("last_price"),
                        "factors": p.get("factors"),
                        "thesis_summary": (p.get("thesis") or "")[:500] or None,
                    }
                    for p in picks
                ]
            )
        except Exception:  # noqa: BLE001 - track record is additive, never fatal
            logger.warning("pick entries insert failed", exc_info=True)

        degraded = (
            failed_analysts > 0
            or checks is None
            or bool(skipped_for_budget)
        )
        return await finalize("partial" if degraded else "completed", payload, stats)

    except Exception:
        logger.exception("stock picks run failed")
        return await finalize("error", None, None, error=traceback.format_exc())
    finally:
        set_current_user_id(None)
