"""Eval-harness plumbing (no live API): golden files parse, fake dispatch,
judge verdict parsing, deterministic checks, regression gate."""

import json

import pytest

from evals.classifier_eval import load_headlines
from evals.fake_tools import build_fake_dispatch
from evals.judge import parse_verdict
from evals.report import regressions
from evals.run import _deterministic_checks, load_cases
from evals.schema import CaseResult, Verdict


def test_golden_chat_cases_parse_and_are_wellformed():
    cases = load_cases()
    assert len(cases) >= 8
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids)), "duplicate case ids"
    for c in cases:
        assert c.question
        assert c.rubric.criteria, f"{c.id} has no judged criteria"
        for crit in c.rubric.criteria:
            assert crit["id"] and crit["text"]


def test_golden_headlines_parse_with_valid_labels():
    rows = load_headlines()
    assert len(rows) >= 25
    assert {r["expected_signal"] for r in rows} == {"warning", "opportunity", "neutral"}


async def test_fake_dispatch_serves_fixture_and_flags_misses():
    misses: list[str] = []
    dispatch = build_fake_dispatch(
        {"get_quote": {"default": {"quotes": [{"ticker": "NVDA"}]}}}, misses
    )
    result = await dispatch["get_quote"]({"tickers": ["NVDA"]}, None)
    assert result["quotes"][0]["ticker"] == "NVDA"
    with pytest.raises(RuntimeError, match="fixture miss"):
        await dispatch["get_portfolio"]({}, None)
    assert misses == ["get_portfolio"]


async def test_fake_dispatch_scripted_error_raises():
    dispatch = build_fake_dispatch({"search_news": {"error": "provider down"}}, [])
    with pytest.raises(RuntimeError, match="provider down"):
        await dispatch["search_news"]({"query": "NVDA"}, None)


def test_parse_verdict_happy_path():
    text = json.dumps(
        {
            "criteria": [{"id": "a", "pass": True, "reasoning": "cites $171.20"}],
            "hallucinations": [],
            "overall_pass": True,
        }
    )
    v = parse_verdict(text, ["a"])
    assert v is not None and v.overall_pass


def test_parse_verdict_hallucination_forces_fail_even_if_judge_says_pass():
    text = json.dumps(
        {
            "criteria": [{"id": "a", "pass": True, "reasoning": "ok"}],
            "hallucinations": ["claimed a 5-year return of 300%"],
            "overall_pass": True,  # judge contradiction — code wins
        }
    )
    v = parse_verdict(text, ["a"])
    assert v is not None and v.overall_pass is False


def test_parse_verdict_rejects_missing_criterion_and_fences_ok():
    assert parse_verdict('{"criteria": []}', ["a"]) is None
    fenced = "```json\n" + json.dumps(
        {"criteria": [{"id": "a", "pass": False, "reasoning": "no"}],
         "hallucinations": [], "overall_pass": False}
    ) + "\n```"
    v = parse_verdict(fenced, ["a"])
    assert v is not None and v.overall_pass is False


def test_deterministic_checks_mentions_and_forbidden():
    case = load_cases()[0]  # portfolio-overview-01: must mention NVDA + SHOP
    assert _deterministic_checks(case, "NVDA up, SHOP.TO down.") == []
    fails = _deterministic_checks(case, "Everything is fine.")
    assert any("NVDA" in f for f in fails)
    fails = _deterministic_checks(
        case, "NVDA and SHOP moved; you should buy more."
    )
    assert any("forbidden" in f for f in fails)


def test_regression_gate_compares_against_baseline():
    baseline = {"prompt_version": "x", "cases": {"a": True, "b": False}}
    results = [
        CaseResult(case_id="a", verdict=Verdict(overall_pass=False)),  # regressed
        CaseResult(case_id="b", verdict=Verdict(overall_pass=False)),  # was failing
        CaseResult(case_id="c", verdict=Verdict(overall_pass=True)),   # new
    ]
    assert regressions(results, baseline) == ["a"]
    assert regressions(results, {}) == []  # no baseline -> nothing to regress
