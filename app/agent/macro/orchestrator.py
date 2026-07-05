"""Macro-scan orchestrator: fan out to the domain specialists, map their
material events to the user's holdings, and emit deduplicated alerts.

Shape (mirrors the digest pipeline's plan→investigate→synthesize seam):
  1. anchor agent_run (trigger='macro')
  2. run the 4 specialists in parallel (each does its own web search)
  3. one synthesis call maps events → holdings → alerts (strict JSON)
  4. each new alert (unique by fingerprint) is stored and enqueued to
     outbound_messages for near-real-time delivery by the Mac worker

Alerts are informational — never buy/sell advice. Delivery reuses the existing
outbound queue; per-user Twilio SMS is a later roadmap phase.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
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
from app.config import DEFAULT_USER_ID, get_settings
from app.db.repo import Repo
from app.observability.logging import Observer
from app.tools import portfolio
from app.tools.registry import ToolContext

_OWNER_USER_ID = uuid.UUID(DEFAULT_USER_ID)


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


async def run_macro_scan(
    db: Repo,
    *,
    user_id: uuid.UUID | None = None,
    client: Any = None,
) -> dict[str, Any]:
    settings = get_settings()
    uid = user_id or _OWNER_USER_ID
    client = _get_client(client)
    ctx = ToolContext(settings=settings, repo=db, user_id=uid)

    started = time.monotonic()
    today = datetime.now(ZoneInfo(settings.tz)).date().isoformat()
    run_id = await db.create_run(
        trigger="macro",
        user_message="[macro scan]",
        model=settings.macro_model,
        prompt_version=PROMPT_VERSION,
        user_id=uid,
    )
    observer = Observer(db, run_id)
    budget = Budget(
        max_iterations=settings.macro_max_iterations,
        max_cost_usd=settings.macro_max_cost_usd,
        model=settings.macro_model,
    )

    try:
        pf = await portfolio.get_portfolio({}, ctx)
        tickers = [p["ticker"] for p in pf.get("positions", [])]

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

        alerts: list[dict[str, Any]] = []
        if events and not budget.exceeded():
            budget.start_iteration()
            context = json.dumps({"holdings": tickers, "findings": events}, default=str)
            content, _ = await call_and_log(
                client,
                model=settings.macro_model,
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

        delivered = await _deliver_alerts(db, run_id, alerts, user_id=uid)

        await db.finalize_run(
            run_id,
            status="completed",
            final_answer=json.dumps({"alerts": len(alerts), "delivered": len(delivered)}),
            iterations=budget.iterations,
            input_tokens=budget.input_tokens,
            output_tokens=budget.output_tokens,
            cost_usd=budget.cost_usd,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        return {
            "run_id": str(run_id),
            "status": "completed",
            "user_id": str(uid),
            "events_found": len(events),
            "alerts": delivered,
        }

    except Exception:
        await db.finalize_run(
            run_id,
            status="error",
            final_answer=None,
            iterations=budget.iterations,
            input_tokens=budget.input_tokens,
            output_tokens=budget.output_tokens,
            cost_usd=budget.cost_usd,
            latency_ms=int((time.monotonic() - started) * 1000),
            error_detail=traceback.format_exc(),
        )
        return {"run_id": str(run_id), "status": "error", "user_id": str(uid), "alerts": []}


async def run_macro_scans_for_all(db: Repo, *, client: Any = None) -> list[dict[str, Any]]:
    """Scheduled entry point: scan every active user independently."""
    results: list[dict[str, Any]] = []
    for uid in await db.list_active_user_ids():
        set_current_user_id(uid)
        try:
            results.append(await run_macro_scan(db, user_id=uid, client=client))
        finally:
            set_current_user_id(None)
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
        await db.enqueue_outbound(message, user_id=user_id)
        await db.mark_alert_delivered(alert_id)
        delivered.append({**alert, "id": str(alert_id)})
    return delivered
