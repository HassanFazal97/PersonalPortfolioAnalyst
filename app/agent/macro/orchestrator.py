"""Macro-scan orchestrator.

Cost-critical design: geopolitical/Fed/energy events are the *same for everyone*,
so the expensive part (four web-searching specialists) runs **once globally**;
only the cheap mapping of those events to a given user's holdings runs per user,
on the cheap classifier model. This keeps macro affordable at scale:

  global scan (once):  4 specialists + web search  → events
  per user (cheap):    Haiku synthesis (events → their tickers) → alerts

Each new alert (unique by fingerprint) is stored and enqueued to
outbound_messages for delivery. Alerts are informational — never buy/sell advice.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import traceback
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.agent.budget import Budget
from app.agent.loop import call_and_log
from app.agent.macro import specialists
from app.agent.prompts import MACRO_SYNTHESIS_PROMPT, PROMPT_VERSION
from app.auth.context import set_current_user_id
from app.config import DEFAULT_USER_ID, get_settings, monthly_cost_cap
from app.db.repo import Repo
from app.observability.logging import Observer
from app.plans import effective_plan
from app.tools import portfolio
from app.tools.registry import ToolContext

_OWNER_USER_ID = uuid.UUID(DEFAULT_USER_ID)

logger = logging.getLogger(__name__)


def _get_client(client: Any) -> Any:
    if client is not None:
        return client
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=get_settings().anthropic_api_key)


def _strip_fences(text: str) -> str:
    return specialists._strip_fences(text)


def _fingerprint(alert: dict[str, Any]) -> str:
    raw = alert.get("fingerprint")
    if isinstance(raw, str) and raw.strip():
        return f"{alert.get('category', 'macro')}:{raw.strip().lower()}"
    digest = hashlib.sha256((alert.get("headline") or "").encode()).hexdigest()[:16]
    return f"{alert.get('category', 'macro')}:{digest}"


def format_alert_message(alert: dict[str, Any]) -> str:
    """Outbound text: headline first, then body (plain text, no markdown)."""
    headline = (alert.get("headline") or "").strip()
    body = (alert.get("body") or "").strip()
    if headline and body:
        return f"{headline}\n\n{body}"
    return headline or body


def parse_alerts(text: str) -> list[dict[str, Any]]:
    """Parse synthesis output into clean alert dicts (never raises)."""
    try:
        data = json.loads(_strip_fences(text))
    except (json.JSONDecodeError, TypeError):
        return []
    rows = data.get("alerts") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("headline") or not row.get("body"):
            continue
        category = row.get("category")
        severity = row.get("severity")
        out.append(
            {
                "category": category if category in specialists.CATEGORIES else "geopolitical",
                "severity": severity if severity in ("low", "medium", "high") else "medium",
                "headline": str(row["headline"]),
                "body": str(row["body"])[:300],
                "tickers": [str(t) for t in row.get("tickers", []) if isinstance(t, str)],
                "fingerprint": _fingerprint(row),
            }
        )
    return out


async def scan_global_events(
    db: Repo, *, client: Any, today: str
) -> tuple[uuid.UUID, list[dict[str, Any]]]:
    """Run the 4 specialists ONCE (web search) and return their events.

    Attributed to the owner; this is the expensive, shared step. Returns
    (scan_run_id, events)."""
    settings = get_settings()
    started = time.monotonic()
    set_current_user_id(_OWNER_USER_ID)
    run_id = await db.create_run(
        trigger="macro",
        user_message="[macro global scan]",
        model=settings.macro_model,
        prompt_version=PROMPT_VERSION,
        user_id=_OWNER_USER_ID,
    )
    observer = Observer(db, run_id)
    budget = Budget(
        max_iterations=settings.macro_max_iterations,
        max_cost_usd=settings.macro_max_cost_usd,
        model=settings.macro_model,
    )
    status, events = "completed", []
    error = None
    try:
        findings = await asyncio.gather(
            *(
                specialists.run_specialist(
                    client=client,
                    model=settings.macro_model,
                    observer=observer,
                    budget=budget,
                    category=category,
                    today=today,
                    iteration_base=(idx + 1) * 10,
                )
                for idx, category in enumerate(specialists.CATEGORIES)
                if not budget.exceeded()
            )
        )
        events = [e for group in findings for e in group]
    except Exception:
        status, error = "error", traceback.format_exc()
    finally:
        set_current_user_id(None)
    await db.finalize_run(
        run_id,
        status=status,
        final_answer=json.dumps({"events": len(events)}),
        iterations=budget.iterations,
        input_tokens=budget.input_tokens,
        output_tokens=budget.output_tokens,
        cost_usd=budget.cost_usd,
        latency_ms=int((time.monotonic() - started) * 1000),
        error_detail=error,
    )
    return run_id, events


async def synthesize_for_user(
    db: Repo,
    *,
    client: Any,
    user_id: uuid.UUID,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Cheap per-user step: map cached global events to this user's holdings and
    deliver new alerts. Runs on the classifier (Haiku) model."""
    settings = get_settings()
    ctx = ToolContext(settings=settings, repo=db, user_id=user_id)
    started = time.monotonic()
    set_current_user_id(user_id)
    run_id = await db.create_run(
        trigger="macro",
        user_message="[macro synthesis]",
        model=settings.classifier_model,
        prompt_version=PROMPT_VERSION,
        user_id=user_id,
    )
    observer = Observer(db, run_id)
    budget = Budget(max_iterations=3, max_cost_usd=0.20, model=settings.classifier_model)
    status, delivered = "completed", []
    error = None
    try:
        pf = await portfolio.get_portfolio({}, ctx)
        tickers = [p["ticker"] for p in pf.get("positions", [])]
        alerts: list[dict[str, Any]] = []
        if tickers and events:
            budget.start_iteration()
            context = json.dumps({"holdings": tickers, "findings": events}, default=str)
            content, _ = await call_and_log(
                client,
                model=settings.classifier_model,
                system_prompt=MACRO_SYNTHESIS_PROMPT,
                messages=[{"role": "user", "content": context}],
                tools=None,
                observer=observer,
                iteration=1,
                budget=budget,
            )
            text = "\n".join(
                b.get("text", "") for b in content if b.get("type") == "text"
            ).strip()
            alerts = parse_alerts(text)
        delivered = await _deliver_alerts(db, run_id, alerts, user_id=user_id)
    except Exception:
        status, error = "error", traceback.format_exc()
    finally:
        set_current_user_id(None)
    await db.finalize_run(
        run_id,
        status=status,
        final_answer=json.dumps({"delivered": len(delivered)}),
        iterations=budget.iterations,
        input_tokens=budget.input_tokens,
        output_tokens=budget.output_tokens,
        cost_usd=budget.cost_usd,
        latency_ms=int((time.monotonic() - started) * 1000),
        error_detail=error,
    )
    return {"user_id": str(user_id), "status": status, "alerts": delivered}


async def run_macro_scan(
    db: Repo,
    *,
    user_id: uuid.UUID | None = None,
    client: Any = None,
) -> dict[str, Any]:
    """Single-user scan (manual / owner): one global scan, then synthesize for
    this user. Scheduled fan-out should use ``run_macro_scans_for_all``."""
    settings = get_settings()
    uid = user_id or _OWNER_USER_ID
    client = _get_client(client)
    today = datetime.now(ZoneInfo(settings.tz)).date().isoformat()
    scan_run_id, events = await scan_global_events(db, client=client, today=today)
    result = await synthesize_for_user(db, client=client, user_id=uid, events=events)
    return {
        "scan_run_id": str(scan_run_id),
        "events_found": len(events),
        **result,
    }


async def run_macro_scans_for_all(db: Repo, *, client: Any = None) -> list[dict[str, Any]]:
    """Scheduled entry point: scan the world ONCE, then a cheap per-user
    synthesis for each Pro recipient under their monthly cost cap."""
    settings = get_settings()
    recipients = await db.list_macro_recipients()
    if not recipients:
        return []
    client = _get_client(client)
    today = datetime.now(ZoneInfo(settings.tz)).date().isoformat()

    scan_run_id, events = await scan_global_events(db, client=client, today=today)
    results: list[dict[str, Any]] = [
        {"scan_run_id": str(scan_run_id), "events_found": len(events)}
    ]
    if not events:
        return results

    for uid in recipients:
        # One user's failure (e.g. a transient DB error in the cost-cap read)
        # must not abort the rest of the batch — same shape as run_digests_for_all.
        try:
            if uid != _OWNER_USER_ID:
                user = await db.get_user(uid)
                # Trial users are pro here (recipients query already excludes
                # lapsed-trial users pending a decision).
                plan = effective_plan(user)
                if await db.monthly_cost_usd(uid) >= monthly_cost_cap(plan, settings):
                    results.append({"user_id": str(uid), "status": "skipped_cost_cap"})
                    continue
            results.append(
                await synthesize_for_user(db, client=client, user_id=uid, events=events)
            )
        except Exception:  # noqa: BLE001 - per-user isolation in the fan-out
            logger.exception("macro synthesis failed for user %s", uid)
            results.append({"user_id": str(uid), "status": "error"})
    return results


async def _deliver_alerts(
    db: Repo,
    run_id: Any,
    alerts: list[dict[str, Any]],
    *,
    user_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Store each new alert and enqueue it for delivery. Dedup by fingerprint
    means a recurring scan that re-sees an event silently skips it."""
    delivered: list[dict[str, Any]] = []
    for alert in alerts:
        alert_id = await db.create_alert_if_new(
            run_id=run_id,
            category=alert["category"],
            severity=alert["severity"],
            headline=alert["headline"],
            body=alert["body"],
            tickers=alert["tickers"],
            fingerprint=alert["fingerprint"],
            user_id=user_id,
        )
        if alert_id is None:
            continue
        message = format_alert_message(alert)
        await db.enqueue_outbound(
            message,
            user_id=user_id,
            kind="alert",
            subject=f"Portfolio alert: {alert['headline'][:80]}",
        )
        await db.mark_alert_delivered(alert_id)
        delivered.append({**alert, "id": str(alert_id)})
    return delivered
