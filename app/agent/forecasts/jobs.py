"""The nightly forecast-ledger job: extract, then resolve.

Runs after the daily prices sync (FORECAST_LEDGER_CRON, prod ``10 19 * *
1-5``) under the owner service context, like every scheduled job. Both phases
are idempotent: extraction re-inserts hit the ``claim_key`` unique index and
vanish, resolution only sweeps rows still ``open``. The extraction window
looks back a few days so a missed night self-heals on the next run.

Phase 1 — extract. Structured sources (picks payloads, deep-dive risk lists,
alerts) map deterministically at $0; prose sources (digest bodies, deep-dive
free-text findings) go through one batched Haiku call per document, cost-
anchored to a ``forecast_extract`` agent run. No client -> prose sources are
skipped and counted, never guessed.

Phase 2 — resolve. Due open rows are scored by the pure math in
``app/quant/forecastscore.py`` against stored adjusted closes; claim types
that prices can't settle (event, volatility) expire at their due date —
kept for the dataset, excluded from every score.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from datetime import time as dt_time
from typing import Any

from app.agent.budget import Budget
from app.agent.forecasts import extract, mappers
from app.agent.prompts import PROMPT_VERSION
from app.config import DEFAULT_USER_ID, Settings
from app.db.repo import Repo
from app.observability.logging import Observer
from app.quant import forecastscore
from app.tools import price_store

logger = logging.getLogger(__name__)

EXTRACT_LOOKBACK_DAYS = 3
EXTRACT_MAX_COST_USD = 0.50  # nightly Haiku spend hard cap
ANOMALY_CATEGORY = "price_anomaly"


async def _extract_structured(
    repo: Repo, since: datetime, stats: dict[str, Any]
) -> list[dict[str, Any]]:
    """$0 deterministic mappers over picks runs, deep-dive risks, alerts."""
    rows: list[dict[str, Any]] = []

    for run in await repo.list_picks_runs(limit=10):
        if (
            run.run_date < since.date()
            or run.status not in ("completed", "partial")
            or run.run_id is None
            or not run.payload
        ):
            continue
        rows.extend(
            mappers.map_picks_run(
                picks_run_id=run.id,
                run_id=run.run_id,
                run_date=run.run_date,
                payload=run.payload,
            )
        )

    for report in await repo.list_deep_dive_reports_since(since):
        if not report.report:
            continue
        rows.extend(
            mappers.map_deep_dive_risks(
                report_id=report.id,
                run_id=report.run_id,
                user_id=report.user_id,
                as_of_date=report.created_at.date(),
                report=report.report,
            )
        )

    skipped_alerts = 0
    for alert in await repo.list_alerts_since(since):
        if alert.run_id is None:
            skipped_alerts += 1  # no reasoning trace, no ledger row
            continue
        row = mappers.map_alert(
            alert_id=alert.id,
            run_id=alert.run_id,
            user_id=alert.user_id,
            source="anomaly" if alert.category == ANOMALY_CATEGORY else "macro",
            as_of_date=alert.created_at.date(),
            headline=alert.headline,
            severity=alert.severity,
            tickers=list(alert.tickers or []),
        )
        if row is not None:
            rows.append(row)
    stats["alerts_without_run"] = skipped_alerts
    return rows


def _deep_dive_document(report: dict[str, Any]) -> str:
    """The prose the Haiku pass reads: free-text findings and opportunities
    (typed risks were already mapped deterministically). Built verbatim from
    the report's own strings so the extractor's quote check can hold."""
    lines: list[str] = []
    for section in report.get("sections") or []:
        for finding in section.get("findings") or []:
            if finding.get("verification") == "challenged":
                continue  # a corrected claim must not enter the ledger
            claim = (finding.get("claim") or "").strip()
            if claim:
                lines.append(claim)
    for opp in report.get("opportunities") or []:
        text = (opp.get("text") or "").strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


async def _extract_prose(
    repo: Repo,
    settings: Settings,
    client: Any,
    since: datetime,
    stats: dict[str, Any],
) -> list[dict[str, Any]]:
    """One Haiku call per prose document, cost-anchored to its own run."""
    docs: list[dict[str, Any]] = []
    for digest in await repo.list_digests_since(since):
        docs.append(
            {
                "source": "digest",
                "text": digest.body,
                "run_id": digest.run_id,
                "user_id": digest.user_id,
                "source_ref": digest.id,
                "as_of_date": digest.digest_date,
            }
        )
    for report in await repo.list_deep_dive_reports_since(since):
        text = _deep_dive_document(report.report or {})
        if text:
            docs.append(
                {
                    "source": "deep_dive",
                    "text": text,
                    "run_id": report.run_id,
                    "user_id": report.user_id,
                    "source_ref": report.id,
                    "as_of_date": report.created_at.date(),
                }
            )
    if not docs:
        return []
    if client is None:
        stats["prose_docs_skipped_no_client"] = len(docs)
        return []

    model = settings.classifier_model
    started = time.monotonic()
    run_id = await repo.create_run(
        trigger="forecast_extract",
        user_message=f"[forecast extraction over {len(docs)} documents]",
        model=model,
        prompt_version=extract.FORECAST_EXTRACTOR_VERSION,
        user_id=DEFAULT_USER_ID,
    )
    observer = Observer(repo, run_id)
    budget = Budget(
        max_iterations=len(docs) + 1,
        max_cost_usd=EXTRACT_MAX_COST_USD,
        model=model,
    )

    rows: list[dict[str, Any]] = []
    drops_total: dict[str, int] = {}
    failures = 0
    skipped_for_budget = 0
    for i, doc in enumerate(docs):
        if budget.cost_exceeded():
            skipped_for_budget += 1
            continue
        try:
            claims, drops, usage, log = await extract.extract_claims(
                client, model, doc["text"]
            )
        except Exception:  # noqa: BLE001 - one bad document never kills the job
            logger.warning("forecast extraction failed for one document", exc_info=True)
            failures += 1
            continue
        budget.record_usage(usage["input_tokens"], usage["output_tokens"])
        await observer.model_call(
            iteration=i + 1, request=log["request"], response=log["response"], usage=usage
        )
        for k, v in drops.items():
            drops_total[k] = drops_total.get(k, 0) + v
        for claim in claims:
            rows.append(
                mappers.build_row(
                    source=doc["source"],
                    run_id=doc["run_id"],
                    user_id=doc["user_id"],
                    source_ref=doc["source_ref"],
                    claim_type=claim["claim_type"],
                    claim_text=claim["claim_text"],
                    tickers=claim["tickers"],
                    direction=claim["direction"],
                    horizon_days=claim["horizon_days"],
                    as_of_date=doc["as_of_date"],
                    confidence_verbal=claim["confidence_verbal"],
                    probability=None,  # verbal prior fills in
                    extractor="haiku",
                    extractor_version=extract.FORECAST_EXTRACTOR_VERSION,
                    magnitude_min_pct=claim["magnitude_min_pct"],
                    pipeline_prompt_version=PROMPT_VERSION,
                    extraction_model=model,
                )
            )

    await repo.finalize_run(
        run_id,
        status="completed" if failures < len(docs) else "error",
        final_answer=f"{len(rows)} claims from {len(docs)} documents",
        iterations=len(docs),
        input_tokens=budget.input_tokens,
        output_tokens=budget.output_tokens,
        cost_usd=budget.cost_usd,
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    stats["prose_docs"] = len(docs)
    stats["prose_failures"] = failures
    if skipped_for_budget:
        stats["prose_docs_skipped_for_budget"] = skipped_for_budget
    stats["extraction_drops"] = drops_total
    stats["extraction_cost_usd"] = round(budget.cost_usd, 4)
    return rows


async def _resolve_due(repo: Repo, today: date, stats: dict[str, Any]) -> None:
    due = await repo.list_due_forecasts(today)
    if not due:
        stats["resolved"] = stats["expired"] = 0
        return

    resolvable = [
        f for f in due if f.claim_type in forecastscore.RESOLVABLE_CLAIM_TYPES
    ]
    expired = 0
    for f in due:
        if f.claim_type not in forecastscore.RESOLVABLE_CLAIM_TYPES:
            await repo.resolve_forecast(
                f.id,
                status="expired",
                resolver_version=forecastscore.RESOLVER_VERSION,
            )
            expired += 1

    resolved = still_open = 0
    if resolvable:
        tickers = sorted(
            {f.primary_ticker for f in resolvable if f.primary_ticker}
        )
        earliest = min(f.as_of_date for f in resolvable)
        series = await repo.get_daily_prices_bulk(
            tickers, since=earliest - timedelta(days=7)
        )
        prices = {
            t: [(r.price_date, float(r.adj_close)) for r in rows]
            for t, rows in series.items()
        }
        bench_days = (today - earliest).days + 21
        benchmark = [
            (date.fromisoformat(r["date"]), float(r["adj_close"]))
            for r in await price_store.get_adjusted_closes(
                repo, mappers.BENCHMARK_TICKER, bench_days
            )
        ]
        for f in resolvable:
            claim = {
                "claim_type": f.claim_type,
                "primary_ticker": f.primary_ticker,
                "direction": f.direction,
                "horizon_days": f.horizon_days,
                "as_of_date": f.as_of_date,
                "due_date": f.due_date,
                "probability": float(f.probability) if f.probability is not None else None,
                "magnitude_min_pct": (
                    float(f.magnitude_min_pct) if f.magnitude_min_pct is not None else None
                ),
            }
            result = forecastscore.resolve_forecast(claim, prices, benchmark)
            if result is None:
                still_open += 1  # benchmark calendar hasn't caught up yet
                continue
            await repo.resolve_forecast(
                f.id,
                status="resolved",
                outcome=result["outcome"],
                realized_value=result["realized_value"],
                benchmark_value=result["benchmark_value"],
                brier=result["brier"],
                resolution_detail=result["resolution_detail"],
                resolver_version=forecastscore.RESOLVER_VERSION,
            )
            resolved += 1

    stats["resolved"] = resolved
    stats["expired"] = expired
    stats["still_open"] = still_open


async def run_forecast_ledger(
    repo: Repo,
    settings: Settings,
    *,
    client: Any = None,
    today: date | None = None,
    lookback_days: int = EXTRACT_LOOKBACK_DAYS,
) -> dict[str, Any]:
    """Extract new forecast rows from recent pipeline outputs, then resolve
    every open row whose horizon has elapsed. Returns a stats payload (the
    heartbeat wrapper stores it). ``lookback_days`` widens the extraction
    window (scripts/backfill_forecasts.py passes months; the nightly cron
    keeps the small self-healing default)."""
    today = today or date.today()
    since = datetime.combine(
        today - timedelta(days=lookback_days), dt_time.min, tzinfo=timezone.utc
    )
    stats: dict[str, Any] = {"as_of": today.isoformat()}

    rows = await _extract_structured(repo, since, stats)
    rows += await _extract_prose(repo, settings, client, since, stats)
    stats["candidate_rows"] = len(rows)
    stats["inserted"] = await repo.insert_forecasts_if_new(rows) if rows else 0

    await _resolve_due(repo, today, stats)
    logger.info("forecast ledger run: %s", stats)
    return stats
