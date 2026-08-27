"""Hypothesis-driven deep dive: plan parsing, theses validation, ledger mapping."""

from __future__ import annotations

import datetime as dt
import json
import uuid

from app.agent.deep_dive.pipeline import (
    _findings_blob,
    _questions_message,
    clean_theses,
    parse_plan,
    parse_report,
)
from app.agent.forecasts import mappers

RUN_ID, REF_ID, USER_ID = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
D = dt.date(2026, 8, 27)

PLAN = {
    "hypotheses": [
        {"id": "H1", "statement": "NVDA premium unsupported", "confirm": "c", "refute": "r"},
        {"statement": "no id provided"},
        {"bogus": True},
    ],
    "questions": {"fundamentals": ["Q1"], "technical": ["Q2"], "risk": [], "news_macro": ["Q3"]},
}


def test_parse_plan_hypotheses_and_questions():
    questions, hyps = parse_plan(json.dumps(PLAN))
    assert questions == {"fundamentals": ["Q1"], "technical": ["Q2"], "news_macro": ["Q3"]}
    assert len(hyps) == 2  # bogus dict dropped
    assert hyps[0]["id"] == "H1"
    assert hyps[1]["id"] == "H2"  # auto-assigned


def test_parse_plan_degrades_gracefully():
    assert parse_plan("garbage") == (None, [])
    # Valid hypotheses but broken questions: hypotheses survive.
    q, hyps = parse_plan(json.dumps({"hypotheses": PLAN["hypotheses"], "questions": []}))
    assert q is None and len(hyps) == 2


def test_questions_message_carries_hypotheses():
    msg = _questions_message(["Q1"], [{"id": "H1", "statement": "S", "confirm": "c", "refute": "r"}])
    assert "HYPOTHESES UNDER TEST" in msg and "H1: S" in msg
    assert "FOR and AGAINST" in msg
    assert _questions_message(["Q1"]).startswith("Research questions")


def test_findings_blob_includes_hypotheses():
    blob = _findings_blob("CTX", {"risk": "F"}, None, [], [{"id": "H1", "statement": "S"}])
    assert "H1: S" in blob and "SPECIALIST FINDINGS" in blob


VALID_THESIS = {
    "claim_text": "NVDA should outperform the index over the quarter.",
    "tickers": ["NVDA"],
    "direction": "outperform",
    "horizon": "3m",
    "confidence": "medium",
}


def test_clean_theses_enum_gate_and_cap():
    raw = [
        VALID_THESIS,
        {**VALID_THESIS, "direction": "moon"},        # bad enum
        {**VALID_THESIS, "horizon": "10y"},            # bad horizon
        {**VALID_THESIS, "claim_text": "  "},          # empty claim
        "not a dict",
        {**VALID_THESIS, "claim_text": "A"},
        {**VALID_THESIS, "claim_text": "B"},
        {**VALID_THESIS, "claim_text": "C"},           # over the cap of 3
    ]
    out = clean_theses(raw)
    assert [t["claim_text"] for t in out] == [VALID_THESIS["claim_text"], "A", "B"]


def test_parse_report_validates_theses():
    report = parse_report(json.dumps({"overview": "x", "theses": [VALID_THESIS, {"junk": 1}]}))
    assert len(report["theses"]) == 1
    # Reports without theses (schema v1 replays) normalize to [].
    assert parse_report(json.dumps({"overview": "x"}))["theses"] == []


def test_map_deep_dive_theses_exact_rows():
    report = {
        "theses": [
            VALID_THESIS,
            {"claim_text": "MU may drift lower this month.", "tickers": ["MU"],
             "direction": "down", "horizon": "1m", "confidence": "low"},
        ]
    }
    rows = mappers.map_deep_dive_theses(
        report_id=REF_ID, run_id=RUN_ID, user_id=USER_ID, as_of_date=D, report=report
    )
    assert len(rows) == 2
    rel, direction = rows
    assert rel["claim_type"] == "relative_performance" and rel["benchmark"] == "SPY"
    assert rel["horizon_days"] == 91 and rel["probability"] == 0.62
    assert direction["claim_type"] == "direction" and direction["direction"] == "down"
    assert direction["horizon_days"] == 30
    assert direction["due_date"] == D + dt.timedelta(days=30)
    assert rows[0]["extractor"] == "deterministic"


def test_map_deep_dive_theses_empty_and_missing():
    assert mappers.map_deep_dive_theses(
        report_id=REF_ID, run_id=RUN_ID, user_id=USER_ID, as_of_date=D, report={}
    ) == []
