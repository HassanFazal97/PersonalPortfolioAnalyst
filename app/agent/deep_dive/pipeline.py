"""Deep-dive orchestrator: plan -> parallel specialists -> critic -> synthesize.

All stages hang off one anchor ``agent_runs`` row (trigger='deep_dive') whose
budget accumulates every stage's usage, so the anchor reports the true total
cost. Specialists run as their own ``run_agent`` sub-loops (also trigger
'deep_dive'); the weekly quota counts ``deep_dive_reports`` rows, never runs.

Failure philosophy mirrors the digest pipeline: a failed specialist degrades
the report to 'partial', a failed critic leaves findings 'unverified', a
failed plan or synthesis stage still finalizes the report row — never silent.
"""

from __future__ import annotations

import asyncio
import json
import time
import traceback
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.agent.budget import Budget
from app.agent.deep_dive.specialists import (
    CRITIC_MAX_COST_USD,
    CRITIC_MAX_ITERATIONS,
    CRITIC_TOOLS,
    ROSTER,
    Specialist,
)
from app.agent.digest_pipeline import build_market_context
from app.agent.events import EventCallback, emit
from app.agent.loop import call_and_log, run_agent
from app.agent.prompts import (
    DEEP_DIVE_CRITIC_PROMPT,
    DEEP_DIVE_PLAN_PROMPT,
    DEEP_DIVE_PLAN_RETRY_SUFFIX,
    DEEP_DIVE_SYNTHESIS_PROMPT,
    DEEP_DIVE_SYNTHESIS_RETRY_SUFFIX,
    PROMPT_VERSION,
)
from app.auth.context import set_current_user_id
from app.config import get_settings, monthly_cost_cap
from app.db.repo import Repo
from app.observability.logging import Observer
from app.plans import user_plan_and_tz
from app.tools.registry import ToolContext

REPORT_SCHEMA_VERSION = 1
DISCLAIMER = "Informational only — not investment advice."

_STAGES = ("plan", "research", "verify", "synthesize")

# Used when the planner can't produce a structured plan; every specialist
# still gets one broad question so the dive proceeds.
_FALLBACK_QUESTIONS: dict[str, list[str]] = {
    "fundamentals": ["How are the portfolio's largest holdings valued right now?"],
    "technical": ["Which holdings moved unusually over the last quarter, and how?"],
    "risk": ["What actually drives this portfolio's risk and concentration?"],
    "news_macro": ["What news or macro forces are affecting these holdings this week?"],
}


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


def parse_plan(text: str) -> dict[str, list[str]] | None:
    """Planner output -> {specialist: [questions]}, or None if unparseable."""
    try:
        data = json.loads(_strip_fences(text))
    except (json.JSONDecodeError, TypeError):
        return None
    questions = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(questions, dict):
        return None
    cleaned: dict[str, list[str]] = {}
    for spec in ROSTER:
        qs = questions.get(spec.name)
        if isinstance(qs, list):
            picked = [str(q) for q in qs if q][:3]
            if picked:
                cleaned[spec.name] = picked
    return cleaned or None


def parse_checks(text: str) -> list[dict[str, str]]:
    """Critic output -> normalized checks. Tolerant: garbage -> []."""
    try:
        data = json.loads(_strip_fences(text))
    except (json.JSONDecodeError, TypeError):
        return []
    checks = data.get("checks") if isinstance(data, dict) else None
    if not isinstance(checks, list):
        return []
    cleaned = []
    for c in checks:
        if isinstance(c, dict) and c.get("claim"):
            verdict = c.get("verdict")
            cleaned.append(
                {
                    "claim": str(c["claim"]),
                    "verdict": verdict if verdict in ("verified", "challenged") else "unverified",
                    "note": str(c.get("note", "")),
                }
            )
    return cleaned


def parse_report(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(_strip_fences(text))
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or not data.get("overview"):
        return None
    return data


class _Progress:
    """Owns the stage snapshot: persists it on every transition (reconnect
    rehydration) and mirrors it to the event stream (live UI)."""

    def __init__(
        self, db: Repo, report_id: uuid.UUID, on_event: EventCallback | None
    ) -> None:
        self._db = db
        self._report_id = report_id
        self._on_event = on_event
        self.snapshot: dict[str, Any] = {stage: "pending" for stage in _STAGES}
        # Per-specialist statuses live beside the stage keys so stage("research")
        # transitions don't clobber them.
        self.snapshot["specialists"] = {s.name: "pending" for s in ROSTER}

    async def stage(self, stage: str, status: str) -> None:
        self.snapshot[stage] = status
        await self._persist()
        await emit(
            self._on_event, {"type": "dd_stage", "stage": stage, "status": status}
        )

    async def specialist(self, name: str, status: str, n: int) -> None:
        self.snapshot["specialists"][name] = status
        await self._persist()
        await emit(
            self._on_event,
            {
                "type": "dd_specialist",
                "name": name,
                "status": status,
                "n": n,
                "of": len(ROSTER),
            },
        )

    async def _persist(self) -> None:
        try:
            await self._db.update_deep_dive_report(
                self._report_id, progress=dict(self.snapshot)
            )
        except Exception:  # noqa: BLE001 - progress is advisory, never fatal
            pass


def _questions_message(questions: list[str]) -> str:
    lines = ["Research questions for your specialty:"]
    lines += [f"{i}. {q}" for i, q in enumerate(questions, 1)]
    return "\n".join(lines)


def _findings_blob(
    market_context: str,
    findings: dict[str, str],
    checks: list[dict[str, str]] | None,
    failed: list[str],
) -> str:
    parts = ["MARKET CONTEXT:", market_context, "", "SPECIALIST FINDINGS:"]
    for name, text in findings.items():
        parts.append(f"\n[{name}]\n{text}")
    if failed:
        parts.append(f"\nFAILED SPECIALISTS (no findings): {', '.join(failed)}")
    if checks is not None:
        parts.append("\nVERIFIER CHECKS:")
        parts.append(json.dumps({"checks": checks}))
    else:
        parts.append("\nVERIFIER CHECKS: verifier unavailable — mark all findings unverified.")
    return "\n".join(parts)


async def run_deep_dive(
    db: Repo,
    *,
    user_id: uuid.UUID,
    report_id: uuid.UUID,
    run_id: uuid.UUID,
    client: Any = None,
    on_event: EventCallback | None = None,
) -> dict[str, Any]:
    """Execute the pipeline against an already-created report + anchor run
    (the route creates both so it can return their ids immediately)."""
    settings = get_settings()
    set_current_user_id(user_id)
    client = _get_client(client)
    user = await db.get_user(user_id)
    plan, tz = user_plan_and_tz(user, user_id=user_id, settings=settings)

    ctx = ToolContext(settings=settings, repo=db, user_id=user_id, timezone=tz)
    ctx.run_id = run_id
    ctx.client = client
    observer = Observer(db, run_id)
    budget = Budget(
        max_iterations=settings.deep_dive_max_iterations,
        max_cost_usd=settings.deep_dive_max_cost_usd,
        model=settings.model,
    )
    ctx.budget = budget
    progress = _Progress(db, report_id, on_event)
    started = time.monotonic()

    def cap_hit() -> bool:
        return budget.cost_usd >= settings.deep_dive_max_cost_usd

    async def finalize(
        status: str, report: dict | None, summary: str | None, error: str | None = None
    ) -> dict[str, Any]:
        await db.update_deep_dive_report(
            report_id,
            status=status,
            report=report,
            summary=summary,
            cost_usd=budget.cost_usd,
        )
        await db.finalize_run(
            run_id,
            status="completed" if status in ("completed", "partial") else "error",
            final_answer=summary,
            iterations=budget.iterations,
            input_tokens=budget.input_tokens,
            output_tokens=budget.output_tokens,
            cost_usd=budget.cost_usd,
            latency_ms=int((time.monotonic() - started) * 1000),
            error_detail=error,
        )
        if summary and status in ("completed", "partial"):
            try:
                await db.enqueue_outbound(
                    summary,
                    user_id=user_id,
                    kind="deep_dive",
                    subject="Your portfolio deep dive",
                )
            except Exception:  # noqa: BLE001 - delivery is best-effort
                pass
        await emit(
            on_event,
            {
                "type": "dd_done",
                "report_id": str(report_id),
                "status": status,
                "cost_usd": round(budget.cost_usd, 4),
            },
        )
        return {"report_id": str(report_id), "status": status, "cost_usd": budget.cost_usd}

    try:
        # ---- Stage 1: plan ------------------------------------------------
        await progress.stage("plan", "started")
        market_context = await build_market_context(
            ctx, tz=tz, plan=plan, digest_tickers=[]
        )
        questions = await _plan_questions(
            client, settings.model, observer, budget, market_context
        )
        await progress.stage("plan", "completed")

        # ---- Stage 2: parallel specialists --------------------------------
        await progress.stage("research", "started")
        budget.start_iteration()  # count the fan-out against the anchor
        results = await asyncio.gather(
            *[
                _run_specialist(
                    db,
                    spec,
                    questions.get(spec.name, _FALLBACK_QUESTIONS[spec.name]),
                    user_id=user_id,
                    client=client,
                    settings=settings,
                    anchor_budget=budget,
                    progress=progress,
                    n=i + 1,
                    on_event=on_event,
                )
                for i, spec in enumerate(ROSTER)
            ],
            return_exceptions=True,
        )
        findings: dict[str, str] = {}
        failed: list[str] = []
        for spec, res in zip(ROSTER, results):
            if isinstance(res, BaseException) or not res:
                failed.append(spec.name)
            else:
                findings[spec.name] = res
        await progress.stage("research", "completed" if findings else "failed")
        if not findings:
            return await finalize(
                "error", None, None, error="all specialists failed"
            )

        # ---- Stage 3: adversarial verification ----------------------------
        checks: list[dict[str, str]] | None = None
        if cap_hit():
            await progress.stage("verify", "skipped")
        else:
            await progress.stage("verify", "started")
            checks = await _run_critic(
                db,
                findings,
                user_id=user_id,
                client=client,
                settings=settings,
                anchor_budget=budget,
                on_event=on_event,
            )
            await progress.stage(
                "verify", "completed" if checks is not None else "failed"
            )

        # ---- Stage 4: synthesize -------------------------------------------
        await progress.stage("synthesize", "started")
        report = await _synthesize(
            client,
            settings.model,
            observer,
            budget,
            _findings_blob(market_context, findings, checks, failed),
        )
        report["schema_version"] = REPORT_SCHEMA_VERSION
        report["as_of"] = date.today().isoformat()
        report["failed_specialists"] = failed
        report["disclaimer"] = DISCLAIMER
        report["verification_summary"] = _verification_summary(report, checks)
        summary = (report.get("summary") or report.get("overview") or "")[:1200]
        await progress.stage("synthesize", "completed")

        status = "completed" if not failed and checks is not None else "partial"
        return await finalize(status, report, summary)

    except Exception:
        try:
            return await finalize("error", None, None, error=traceback.format_exc())
        finally:
            pass
    finally:
        set_current_user_id(None)


async def _plan_questions(
    client: Any, model: str, observer: Observer, budget: Budget, market_context: str
) -> dict[str, list[str]]:
    messages = [{"role": "user", "content": market_context}]
    content, _ = await call_and_log(
        client,
        model=model,
        system_prompt=DEEP_DIVE_PLAN_PROMPT,
        messages=messages,
        tools=None,
        observer=observer,
        iteration=1,
        budget=budget,
    )
    parsed = parse_plan(_join_text(content))
    if parsed is not None:
        return parsed
    messages.append({"role": "assistant", "content": content})
    messages.append({"role": "user", "content": DEEP_DIVE_PLAN_RETRY_SUFFIX})
    content, _ = await call_and_log(
        client,
        model=model,
        system_prompt=DEEP_DIVE_PLAN_PROMPT,
        messages=messages,
        tools=None,
        observer=observer,
        iteration=2,
        budget=budget,
    )
    return parse_plan(_join_text(content)) or dict(_FALLBACK_QUESTIONS)


def _forwarder(
    specialist_name: str, label: str, on_event: EventCallback | None
) -> EventCallback | None:
    """Map a specialist sub-run's tool events onto coarse dd_tool events (the
    'activity ticker' in the UI). Text deltas and iterations stay internal."""
    if on_event is None:
        return None

    async def forward(event: dict[str, Any]) -> None:
        if event.get("type") == "tool_start":
            await emit(
                on_event,
                {
                    "type": "dd_tool",
                    "specialist": specialist_name,
                    "specialist_label": label,
                    "name": event.get("name"),
                    "label": event.get("label"),
                },
            )

    return forward


async def _run_specialist(
    db: Repo,
    spec: Specialist,
    questions: list[str],
    *,
    user_id: uuid.UUID,
    client: Any,
    settings: Any,
    anchor_budget: Budget,
    progress: _Progress,
    n: int,
    on_event: EventCallback | None,
) -> str | None:
    """One specialist sub-run. Returns findings text, or None on failure —
    exceptions never propagate (a dead specialist degrades, not aborts)."""
    await progress.specialist(spec.name, "running", n)
    sub_budget = Budget(
        max_iterations=spec.max_iterations,
        max_cost_usd=spec.max_cost_usd,
        model=settings.model,
    )
    try:
        sub = await run_agent(
            _questions_message(questions),
            trigger="deep_dive",
            system_prompt=spec.system_prompt,
            tools=spec.tools,
            budget=sub_budget,
            db=db,
            client=client,
            user_id=user_id,
            on_event=_forwarder(spec.name, spec.label, on_event),
        )
        answer = (sub.answer or "").strip()
        await progress.specialist(spec.name, "completed" if answer else "failed", n)
        return answer or None
    except Exception:  # noqa: BLE001 - partial reports over dead dives
        await progress.specialist(spec.name, "failed", n)
        return None
    finally:
        # Fold the sub-run into the anchor so its row shows the true total.
        anchor_budget.record_usage(sub_budget.input_tokens, sub_budget.output_tokens)


async def _run_critic(
    db: Repo,
    findings: dict[str, str],
    *,
    user_id: uuid.UUID,
    client: Any,
    settings: Any,
    anchor_budget: Budget,
    on_event: EventCallback | None,
) -> list[dict[str, str]] | None:
    """Adversarial verification sub-run. None means the critic itself failed
    (findings stay 'unverified'); an empty list means it found nothing to check."""
    sub_budget = Budget(
        max_iterations=CRITIC_MAX_ITERATIONS,
        max_cost_usd=CRITIC_MAX_COST_USD,
        model=settings.model,
    )
    draft = "\n\n".join(f"[{name}]\n{text}" for name, text in findings.items())
    try:
        sub = await run_agent(
            f"DRAFT FINDINGS TO VERIFY:\n\n{draft}",
            trigger="deep_dive",
            system_prompt=DEEP_DIVE_CRITIC_PROMPT,
            tools=CRITIC_TOOLS,
            budget=sub_budget,
            db=db,
            client=client,
            user_id=user_id,
            on_event=_forwarder("critic", "Verification analyst", on_event),
        )
        return parse_checks(sub.answer or "")
    except Exception:  # noqa: BLE001
        return None
    finally:
        anchor_budget.record_usage(sub_budget.input_tokens, sub_budget.output_tokens)


async def _synthesize(
    client: Any, model: str, observer: Observer, budget: Budget, blob: str
) -> dict[str, Any]:
    messages = [{"role": "user", "content": blob}]
    content, _ = await call_and_log(
        client,
        model=model,
        system_prompt=DEEP_DIVE_SYNTHESIS_PROMPT,
        messages=messages,
        tools=None,
        observer=observer,
        iteration=budget.iterations + 1,
        budget=budget,
        max_tokens=3000,  # the structured report JSON outgrows the 1024 default
    )
    text = _join_text(content)
    report = parse_report(text)
    if report is not None:
        return report
    messages.append({"role": "assistant", "content": content})
    messages.append({"role": "user", "content": DEEP_DIVE_SYNTHESIS_RETRY_SUFFIX})
    content, _ = await call_and_log(
        client,
        model=model,
        system_prompt=DEEP_DIVE_SYNTHESIS_PROMPT,
        messages=messages,
        tools=None,
        observer=observer,
        iteration=budget.iterations + 2,
        budget=budget,
        max_tokens=3000,
    )
    text2 = _join_text(content)
    report = parse_report(text2)
    if report is not None:
        return report
    # Text-only fallback: the user still gets something readable.
    raw = text2 or text or "The deep dive could not produce a structured report."
    return {"overview": raw, "summary": raw[:900], "sections": []}


def _verification_summary(
    report: dict[str, Any], checks: list[dict[str, str]] | None
) -> dict[str, int]:
    if not checks:
        return {"checked": 0, "verified": 0, "challenged": 0}
    verified = sum(1 for c in checks if c["verdict"] == "verified")
    challenged = sum(1 for c in checks if c["verdict"] == "challenged")
    return {"checked": len(checks), "verified": verified, "challenged": challenged}


async def run_deep_dives_for_all(db: Repo, *, client: Any = None) -> list[dict[str, Any]]:
    """Scheduled weekly fan-out: one dive per eligible Pro user, quota- and
    cap-guarded, idempotent per ISO week (a manual dive counts)."""
    settings = get_settings()
    results: list[dict[str, Any]] = []
    week = timedelta(days=7)
    for uid in await db.list_digest_recipients():
        try:
            user = await db.get_user(uid)
            plan, _tz = user_plan_and_tz(user, user_id=uid, settings=settings)
            if plan != "pro":
                continue
            used, _oldest = await db.deep_dive_usage_since(
                uid, datetime.now(timezone.utc) - week
            )
            if used > 0:
                results.append({"user_id": str(uid), "status": "skipped_exists"})
                continue
            if await db.monthly_cost_usd(uid) >= monthly_cost_cap(plan, settings):
                results.append({"user_id": str(uid), "status": "skipped_cost_cap"})
                continue
            set_current_user_id(uid)
            run_id = await db.create_run(
                trigger="deep_dive",
                user_message="[portfolio deep dive]",
                model=settings.model,
                prompt_version=PROMPT_VERSION,
                user_id=uid,
            )
            report_id = await db.create_deep_dive_report(run_id=run_id, user_id=uid)
            results.append(
                await run_deep_dive(
                    db, user_id=uid, report_id=report_id, run_id=run_id, client=client
                )
            )
        except Exception:  # noqa: BLE001 - per-user isolation
            results.append({"user_id": str(uid), "status": "error"})
        finally:
            set_current_user_id(None)
    return results
