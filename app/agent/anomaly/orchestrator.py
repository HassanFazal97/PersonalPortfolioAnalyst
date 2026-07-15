"""Price-anomaly orchestrator — fan-out, narration, delivery.

Same cost structure as the macro pipeline, one notch cheaper: the global
step here is *free* (pure detector math over yfinance history — no model
calls at all), and the per-user step is one Haiku call that only narrates
what the math already decided. A narration failure falls back to a
deterministic template — it never suppresses the alert.

  global scan (once):  detectors over every distinct held ticker → flags
  per user (cheap):    cooldown filter → noisy-OR → Haiku narration → alert
"""

from __future__ import annotations

import json
import logging
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.agent.anomaly import synthesis
from app.agent.anomaly.scanner import AnomalyFlag, scan_tickers
from app.agent.budget import Budget
from app.agent.loop import call_and_log
from app.agent.macro.orchestrator import (
    _get_client,
    _strip_fences,
    format_alert_message,
)
from app.agent.prompts import ANOMALY_NARRATION_PROMPT, PROMPT_VERSION
from app.auth.context import set_current_user_id
from app.config import DEFAULT_USER_ID, get_settings, monthly_cost_cap
from app.db.repo import Repo
from app.observability.logging import Observer

_OWNER_USER_ID = uuid.UUID(DEFAULT_USER_ID)

logger = logging.getLogger(__name__)


async def scan_global_anomalies(
    db: Repo,
    *,
    recipients: list[uuid.UUID] | None = None,
) -> tuple[uuid.UUID, dict[str, list[AnomalyFlag]]]:
    """Run the detectors once over every distinct ticker held by ``recipients``
    (default: the scheduled anomaly audience).

    Model-free (cost 0), but still recorded as an owner-attributed run so
    every scan is auditable in /runs alongside macro scans."""
    settings = get_settings()
    started = time.monotonic()
    if recipients is None:
        recipients = await db.list_anomaly_recipients()
    tickers = await db.list_distinct_tickers(recipients)
    run_id = await db.create_run(
        trigger="anomaly",
        user_message=f"[anomaly scan: {len(tickers)} tickers]",
        model="none",
        prompt_version=PROMPT_VERSION,
        user_id=_OWNER_USER_ID,
    )
    status, error = "completed", None
    flags_by_ticker: dict[str, list[AnomalyFlag]] = {}
    try:
        if tickers:
            flags_by_ticker = await scan_tickers(tickers, settings=settings)
    except Exception:
        status, error = "error", traceback.format_exc()
    await db.finalize_run(
        run_id,
        status=status,
        final_answer=json.dumps(
            {
                "tickers_scanned": len(tickers),
                "tickers_flagged": sorted(flags_by_ticker),
            }
        ),
        iterations=0,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        latency_ms=int((time.monotonic() - started) * 1000),
        error_detail=error,
    )
    return run_id, flags_by_ticker


def _narration_payload(flags: list[AnomalyFlag]) -> str:
    return json.dumps({"flags": [f.model_dump() for f in flags]}, default=str)


def _parse_narration(text: str) -> tuple[str, str] | None:
    try:
        data = json.loads(_strip_fences(text))
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    headline = str(data.get("headline") or "").strip()
    body = str(data.get("body") or "").strip()[:300]
    if not headline or not body:
        return None
    return headline, body


async def synthesize_anomalies_for_user(
    db: Repo,
    *,
    client: Any,
    user_id: uuid.UUID,
    flags_by_ticker: dict[str, list[AnomalyFlag]],
) -> dict[str, Any]:
    """Cheap per-user step: intersect global flags with this user's holdings,
    apply the cooldown, aggregate to ONE alert, narrate it, deliver it."""
    settings = get_settings()

    held = {p.ticker for p in await db.list_positions(user_id=user_id)}
    hit_tickers = sorted(held & set(flags_by_ticker))

    # Cooldown: a ticker that appeared in a recent price_anomaly alert stays
    # quiet — the cross-day fatigue backstop (fingerprints only dedup same-day).
    if hit_tickers:
        since = datetime.now(timezone.utc) - timedelta(
            days=settings.anomaly_cooldown_days
        )
        recent = await db.recent_alerts_by_category(
            user_id, category=synthesis.CATEGORY, since=since
        )
        cooled = {t for a in recent for t in (a.tickers or [])}
        hit_tickers = [t for t in hit_tickers if t not in cooled]

    if not hit_tickers:
        return {"user_id": str(user_id), "status": "no_anomalies", "alerts": []}

    flags = [f for t in hit_tickers for f in flags_by_ticker[t]]
    best = synthesis.best_flag_per_ticker(flags)
    combined = synthesis.noisy_or(f.severity for f in best.values())

    started = time.monotonic()
    set_current_user_id(user_id)
    run_id = await db.create_run(
        trigger="anomaly",
        user_message="[anomaly narration]",
        model=settings.classifier_model,
        prompt_version=PROMPT_VERSION,
        user_id=user_id,
    )
    observer = Observer(db, run_id)
    budget = Budget(
        max_iterations=2,
        max_cost_usd=settings.anomaly_max_cost_usd,
        model=settings.classifier_model,
    )
    status, delivered = "completed", []
    error = None
    try:
        narration: tuple[str, str] | None = None
        try:
            budget.start_iteration()
            content, _ = await call_and_log(
                client,
                model=settings.classifier_model,
                system_prompt=ANOMALY_NARRATION_PROMPT,
                messages=[{"role": "user", "content": _narration_payload(flags)}],
                tools=None,
                observer=observer,
                iteration=1,
                budget=budget,
            )
            text = "\n".join(
                b.get("text", "") for b in content if b.get("type") == "text"
            ).strip()
            narration = _parse_narration(text)
        except Exception:
            logger.warning(
                "anomaly narration failed for user %s; using fallback",
                user_id,
                exc_info=True,
            )
        if narration is None:
            # Math already decided this matters — the alert fires regardless.
            narration = synthesis.format_fallback_message(flags, combined)

        headline, body = narration
        scan_date = datetime.now(ZoneInfo(settings.tz)).date()
        alert = {
            "category": synthesis.CATEGORY,
            "severity": synthesis.severity_label(combined),
            "headline": headline,
            "body": body,
            "tickers": hit_tickers,
            "fingerprint": synthesis.build_fingerprint(scan_date, flags),
        }
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
        if alert_id is not None:
            await db.enqueue_outbound(
                format_alert_message(alert),
                user_id=user_id,
                kind="alert",
                subject=f"Price alert: {alert['headline'][:80]}",
            )
            await db.mark_alert_delivered(alert_id)
            delivered.append({**alert, "id": str(alert_id)})
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


async def run_anomaly_scan(
    db: Repo,
    *,
    user_id: uuid.UUID | None = None,
    client: Any = None,
) -> dict[str, Any]:
    """Single-user scan (manual / owner): one global detector pass, then
    synthesis for this user. Scheduled fan-out uses ``run_anomaly_scans_for_all``."""
    uid = user_id or _OWNER_USER_ID
    client = _get_client(client)
    scan_run_id, flags_by_ticker = await scan_global_anomalies(db, recipients=[uid])
    result = await synthesize_anomalies_for_user(
        db, client=client, user_id=uid, flags_by_ticker=flags_by_ticker
    )
    return {
        "scan_run_id": str(scan_run_id),
        "tickers_flagged": len(flags_by_ticker),
        **result,
    }


async def run_anomaly_scans_for_all(
    db: Repo, *, client: Any = None
) -> list[dict[str, Any]]:
    """Scheduled entry point: detectors run ONCE, then a cheap per-user
    narration for each recipient (Pro users) under their cap."""
    settings = get_settings()
    recipients = await db.list_anomaly_recipients()
    if not recipients:
        return []

    scan_run_id, flags_by_ticker = await scan_global_anomalies(db, recipients=recipients)
    results: list[dict[str, Any]] = [
        {"scan_run_id": str(scan_run_id), "tickers_flagged": len(flags_by_ticker)}
    ]
    if not flags_by_ticker:
        return results

    client = _get_client(client)
    for uid in recipients:
        # One user's failure must not abort the rest of the batch — same
        # shape as run_macro_scans_for_all / run_digests_for_all.
        try:
            user = await db.get_user(uid)
            plan = getattr(user, "plan", "free") if user is not None else "free"
            if await db.monthly_cost_usd(uid) >= monthly_cost_cap(plan, settings):
                results.append({"user_id": str(uid), "status": "skipped_cost_cap"})
                continue
            results.append(
                await synthesize_anomalies_for_user(
                    db, client=client, user_id=uid, flags_by_ticker=flags_by_ticker
                )
            )
        except Exception:  # noqa: BLE001 - per-user isolation in the fan-out
            logger.exception("anomaly synthesis failed for user %s", uid)
            results.append({"user_id": str(uid), "status": "error"})
    return results
