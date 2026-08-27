"""Deterministic source-output -> forecast-row mappers ($0 extraction).

Structured pipeline outputs (picks payloads, deep-dive risk lists, alerts)
already contain typed claims — mapping them into ``forecasts`` rows needs no
model call. Free-prose sources (digest bodies, deep-dive free-text findings)
go through the Haiku extractor in ``extract.py`` instead.

Pure functions: dict-shaped source rows in, insert-ready row dicts out.
Idempotency is carried by ``claim_key`` (hash including as_of_date — the DB
unique index makes re-mapping a no-op) and restatement grouping by
``family_key`` (same hash without the date).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from typing import Any

from app.quant.forecastscore import CONFIDENCE_PRIOR_MAP, snap_horizon

FORECAST_MAPPER_VERSION = "2026-08-27.1"

# Shared horizon vocabulary (also used by the Haiku extractor's validator).
HORIZON_VOCAB = {"1w": 7, "1m": 30, "3m": 91, "6m": 182, "unstated": None}

PICKS_HORIZON_DAYS = 91  # the picks cohort's headline horizon
BENCHMARK_TICKER = "SPY"

# A flagged risk is a possibility, not a prediction — its severity maps to a
# deliberately conservative verbal confidence (versioned with the mapper).
SEVERITY_CONFIDENCE_MAP = {"high": "medium", "medium": "low", "low": "speculative"}


def verbal_from_probability(p: float) -> str:
    """Verbal bucket for a Python-computed confidence (picks rows)."""
    if p >= 0.70:
        return "high"
    if p >= 0.60:
        return "medium"
    if p >= 0.50:
        return "low"
    return "speculative"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _key(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def make_keys(
    *,
    source: str,
    user_id: uuid.UUID | None,
    primary_ticker: str | None,
    claim_type: str,
    direction: str | None,
    horizon_days: int,
    as_of_date: dt.date,
) -> tuple[str, str]:
    """(claim_key, family_key). Two claims that agree on everything but the
    issue date share a family; same-day duplicates share the claim_key and
    collapse in the DB."""
    family_parts = [
        source,
        str(user_id or ""),
        primary_ticker or "",
        claim_type,
        direction or "",
        str(horizon_days),
    ]
    return _key(family_parts + [as_of_date.isoformat()]), _key(family_parts)


def build_row(
    *,
    source: str,
    run_id: uuid.UUID,
    user_id: uuid.UUID | None,
    source_ref: uuid.UUID | None,
    claim_type: str,
    claim_text: str,
    tickers: list[str],
    direction: str | None,
    horizon_days: int | None,
    as_of_date: dt.date,
    confidence_verbal: str,
    probability: float | None,
    extractor: str,
    extractor_version: str,
    benchmark: str | None = None,
    magnitude_min_pct: float | None = None,
    magnitude_max_pct: float | None = None,
    pipeline_prompt_version: str | None = None,
    extraction_model: str | None = None,
) -> dict[str, Any]:
    """One insert-ready ``forecasts`` row; horizons snapped, keys derived.
    When no Python-computed probability exists, the versioned verbal-prior
    map fills it so Brier scores stay computable (calibration is still
    reported per verbal bucket)."""
    if probability is None:
        probability = CONFIDENCE_PRIOR_MAP.get(confidence_verbal)
    horizon = snap_horizon(horizon_days, claim_type)
    primary = tickers[0] if tickers else None
    claim_key, family_key = make_keys(
        source=source,
        user_id=user_id,
        primary_ticker=primary,
        claim_type=claim_type,
        direction=direction,
        horizon_days=horizon,
        as_of_date=as_of_date,
    )
    return {
        "run_id": run_id,
        "user_id": user_id,
        "source": source,
        "source_ref": source_ref,
        "source_content_hash": content_hash(claim_text),
        "claim_type": claim_type,
        "claim_text": claim_text,
        "tickers": tickers,
        "primary_ticker": primary,
        "benchmark": benchmark
        or (BENCHMARK_TICKER if claim_type == "relative_performance" or not tickers else None),
        "direction": direction,
        "magnitude_min_pct": magnitude_min_pct,
        "magnitude_max_pct": magnitude_max_pct,
        "horizon_days": horizon,
        "as_of_date": as_of_date,
        "due_date": as_of_date + dt.timedelta(days=horizon),
        "confidence_verbal": confidence_verbal,
        "probability": probability,
        "extractor": extractor,
        "extractor_version": extractor_version,
        "pipeline_prompt_version": pipeline_prompt_version,
        "extraction_model": extraction_model,
        "claim_key": claim_key,
        "family_key": family_key,
        "status": "open",
    }


def map_picks_run(
    *,
    picks_run_id: uuid.UUID,
    run_id: uuid.UUID,
    run_date: dt.date,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Each published pick is one global relative-performance claim vs SPY at
    the 91-day horizon: "this name outperforms the index over the quarter."
    ``probability`` is the pipeline's Python-computed confidence — the ledger
    only mirrors it (the public picks numbers stay with trackrecord.py)."""
    rows = []
    for pick in payload.get("picks") or []:
        ticker = pick.get("ticker")
        if not ticker:
            continue
        confidence = pick.get("confidence")
        probability = float(confidence) if confidence is not None else None
        thesis = (pick.get("thesis") or "").strip()
        claim_text = thesis or f"{ticker} ranked #{pick.get('rank')} by the factor screen"
        rows.append(
            build_row(
                source="picks",
                run_id=run_id,
                user_id=None,  # global claim
                source_ref=picks_run_id,
                claim_type="relative_performance",
                claim_text=claim_text,
                tickers=[ticker],
                direction="outperform",
                horizon_days=PICKS_HORIZON_DAYS,
                as_of_date=run_date,
                confidence_verbal=(
                    verbal_from_probability(probability)
                    if probability is not None
                    else "medium"
                ),
                probability=probability,
                extractor="deterministic",
                extractor_version=FORECAST_MAPPER_VERSION,
                benchmark=BENCHMARK_TICKER,
            )
        )
    return rows


def map_deep_dive_risks(
    *,
    report_id: uuid.UUID,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    as_of_date: dt.date,
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    """The synthesis JSON's typed ``risks`` list maps deterministically to
    risk_warning claims (free-text findings/opportunities go through the
    Haiku extractor instead)."""
    rows = []
    for risk in report.get("risks") or []:
        text = (risk.get("text") or "").strip()
        if not text:
            continue
        severity = risk.get("severity") or "low"
        tickers = [t for t in (risk.get("tickers") or []) if isinstance(t, str)]
        rows.append(
            build_row(
                source="deep_dive",
                run_id=run_id,
                user_id=user_id,
                source_ref=report_id,
                claim_type="risk_warning",
                claim_text=text,
                tickers=tickers,
                direction=None,
                horizon_days=None,  # unstated -> per-type default
                as_of_date=as_of_date,
                confidence_verbal=SEVERITY_CONFIDENCE_MAP.get(severity, "speculative"),
                probability=None,
                extractor="deterministic",
                extractor_version=FORECAST_MAPPER_VERSION,
            )
        )
    return rows


def map_deep_dive_theses(
    *,
    report_id: uuid.UUID,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    as_of_date: dt.date,
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    """The synthesis stage's typed ``theses`` (schema v2, hypothesis-driven
    dives) map deterministically: direction/horizon/confidence are already
    closed-vocabulary (clean_theses validated them at parse time), so no
    model call is needed and the claim is exactly what the report shows the
    user. outperform/underperform read as relative-performance vs SPY."""
    rows = []
    for thesis in report.get("theses") or []:
        direction = thesis.get("direction")
        horizon_days = HORIZON_VOCAB.get(thesis.get("horizon"))
        claim = (thesis.get("claim_text") or "").strip()
        confidence = thesis.get("confidence")
        if not claim or direction is None or confidence is None:
            continue
        claim_type = (
            "relative_performance"
            if direction in ("outperform", "underperform")
            else "direction"
        )
        rows.append(
            build_row(
                source="deep_dive",
                run_id=run_id,
                user_id=user_id,
                source_ref=report_id,
                claim_type=claim_type,
                claim_text=claim,
                tickers=[t for t in thesis.get("tickers") or [] if isinstance(t, str)],
                direction=direction,
                horizon_days=horizon_days,
                as_of_date=as_of_date,
                confidence_verbal=confidence,
                probability=None,  # verbal prior fills in
                extractor="deterministic",
                extractor_version=FORECAST_MAPPER_VERSION,
            )
        )
    return rows


def map_alert(
    *,
    alert_id: uuid.UUID,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    source: str,
    as_of_date: dt.date,
    headline: str,
    severity: str,
    tickers: list[str],
) -> dict[str, Any] | None:
    """A macro/anomaly alert is one risk_warning claim (its headline,
    verbatim). Alerts without an anchoring run are skipped by the caller
    (forecasts.run_id is NOT NULL — no trace, no ledger row)."""
    text = (headline or "").strip()
    if not text:
        return None
    return build_row(
        source=source,
        run_id=run_id,
        user_id=user_id,
        source_ref=alert_id,
        claim_type="risk_warning",
        claim_text=text,
        tickers=[t for t in tickers if isinstance(t, str)],
        direction=None,
        horizon_days=None,
        as_of_date=as_of_date,
        confidence_verbal=SEVERITY_CONFIDENCE_MAP.get(severity, "speculative"),
        probability=None,
        extractor="deterministic",
        extractor_version=FORECAST_MAPPER_VERSION,
    )
