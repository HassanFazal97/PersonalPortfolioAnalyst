"""Deterministic source -> forecast-row mappers: exact expected rows."""

from __future__ import annotations

import datetime as dt
import uuid

from app.agent.forecasts import mappers

RUN_ID = uuid.uuid4()
REF_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
D = dt.date(2026, 8, 20)


def test_map_picks_run_exact_row():
    payload = {
        "picks": [
            {"ticker": "NVDA", "rank": 1, "confidence": 0.72, "thesis": "Momentum leader."},
            {"ticker": "SHOP.TO", "rank": 2, "confidence": 0.58, "thesis": ""},
            {"rank": 3},  # no ticker: skipped
        ]
    }
    rows = mappers.map_picks_run(
        picks_run_id=REF_ID, run_id=RUN_ID, run_date=D, payload=payload
    )
    assert len(rows) == 2
    top = rows[0]
    assert top["source"] == "picks" and top["user_id"] is None
    assert top["claim_type"] == "relative_performance"
    assert top["direction"] == "outperform"
    assert top["primary_ticker"] == "NVDA" and top["benchmark"] == "SPY"
    assert top["horizon_days"] == 91
    assert top["as_of_date"] == D and top["due_date"] == D + dt.timedelta(days=91)
    assert top["probability"] == 0.72 and top["confidence_verbal"] == "high"
    assert top["claim_text"] == "Momentum leader."
    # Missing thesis falls back to a deterministic sentence; 0.58 -> "low".
    assert rows[1]["confidence_verbal"] == "low"
    assert "SHOP.TO" in rows[1]["claim_text"]


def test_map_picks_keys_idempotent_and_family_stable():
    payload = {"picks": [{"ticker": "NVDA", "rank": 1, "confidence": 0.7, "thesis": "T"}]}
    a = mappers.map_picks_run(picks_run_id=REF_ID, run_id=RUN_ID, run_date=D, payload=payload)[0]
    b = mappers.map_picks_run(picks_run_id=uuid.uuid4(), run_id=uuid.uuid4(), run_date=D, payload=payload)[0]
    assert a["claim_key"] == b["claim_key"]  # same claim, same day
    later = mappers.map_picks_run(
        picks_run_id=REF_ID, run_id=RUN_ID, run_date=D + dt.timedelta(days=1), payload=payload
    )[0]
    assert later["claim_key"] != a["claim_key"]
    assert later["family_key"] == a["family_key"]  # restatement, same family


def test_map_deep_dive_risks():
    report = {
        "risks": [
            {"text": "NVDA is 31% of portfolio risk.", "tickers": ["NVDA"], "severity": "high"},
            {"text": "", "severity": "high"},  # empty text: skipped
            {"text": "Rate shock exposure.", "tickers": [], "severity": "low"},
        ],
        "opportunities": [{"text": "ignored here", "tickers": []}],
    }
    rows = mappers.map_deep_dive_risks(
        report_id=REF_ID, run_id=RUN_ID, user_id=USER_ID, as_of_date=D, report=report
    )
    assert len(rows) == 2
    assert all(r["claim_type"] == "risk_warning" for r in rows)
    assert rows[0]["user_id"] == USER_ID
    assert rows[0]["confidence_verbal"] == "medium"  # severity high -> medium
    assert rows[0]["horizon_days"] == 91  # risk default
    # Verbal prior fills probability so Brier stays computable.
    assert rows[0]["probability"] == 0.62
    # Market-level risk: no primary ticker, benchmark is the subject.
    assert rows[1]["primary_ticker"] is None and rows[1]["benchmark"] == "SPY"
    assert rows[1]["confidence_verbal"] == "speculative"


def test_map_alert():
    row = mappers.map_alert(
        alert_id=REF_ID,
        run_id=RUN_ID,
        user_id=USER_ID,
        source="macro",
        as_of_date=D,
        headline="Tariff escalation threatens semiconductor supply chains",
        severity="medium",
        tickers=["NVDA", "AMD"],
    )
    assert row["source"] == "macro" and row["claim_type"] == "risk_warning"
    assert row["primary_ticker"] == "NVDA" and row["tickers"] == ["NVDA", "AMD"]
    assert row["confidence_verbal"] == "low"
    assert mappers.map_alert(
        alert_id=REF_ID, run_id=RUN_ID, user_id=USER_ID, source="macro",
        as_of_date=D, headline="  ", severity="low", tickers=[],
    ) is None
