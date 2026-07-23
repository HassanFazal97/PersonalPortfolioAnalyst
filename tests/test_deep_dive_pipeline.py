"""Deep-dive pipeline: stage flow, partial failure, verification, fallbacks."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest

import app.agent.deep_dive.pipeline as dd
from app.agent.prompts import (
    DEEP_DIVE_PLAN_PROMPT,
    DEEP_DIVE_SYNTHESIS_PROMPT,
)
from tests.fakes import FakeRepo

_PLAN_JSON = json.dumps(
    {
        "questions": {
            "fundamentals": ["How is NVDA valued?"],
            "technical": ["Any unusual moves?"],
            "risk": ["What drives risk?"],
            "news_macro": ["Any news on holdings?"],
        }
    }
)

_CHECKS_JSON = json.dumps(
    {
        "checks": [
            {"claim": "NVDA P/E is 40", "verdict": "verified", "note": "matches"},
            {"claim": "SHOP fell 10%", "verdict": "challenged", "note": "fell 4%"},
        ]
    }
)

_REPORT_JSON = json.dumps(
    {
        "headline": "Portfolio holding up",
        "overview": "A grounded overview.",
        "summary": "Short summary for delivery.",
        "sections": [
            {
                "specialist": "fundamentals",
                "title": "Valuation",
                "findings": [
                    {
                        "claim": "NVDA P/E is 40",
                        "evidence": "get_fundamentals",
                        "tickers": ["NVDA"],
                        "confidence": "high",
                        "verification": "verified",
                        "verification_note": "",
                    }
                ],
            }
        ],
        "risks": [],
        "opportunities": [],
    }
)


def _text(text):
    return {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


class RoutedClient:
    """Fake Anthropic client that routes by system-prompt content, so the
    parallel specialists' nondeterministic call order can't flake the test.
    Routes: list of (marker, responses) — a marker matching the system prompt
    pops the next canned response for it; an Exception response raises."""

    def __init__(self, routes: list[tuple[str, list]]):
        self._routes = [(m, list(rs)) for m, rs in routes]
        self.calls: list[dict] = []

    @property
    def messages(self):
        return self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        system = kwargs.get("system", "")
        if isinstance(system, list):  # cache_control block form
            system = "".join(b.get("text", "") for b in system)
        for marker, responses in self._routes:
            if marker in system and responses:
                resp = responses.pop(0)
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"no scripted route for system prompt: {system[:80]}...")


def _routes(*, plan=None, specialists=None, critic=None, synthesis=None):
    return [
        (DEEP_DIVE_PLAN_PROMPT[:60], plan or [_text(_PLAN_JSON)]),
        # The critic's prompt embeds CHAT_SYSTEM_PROMPT too, so route it by its
        # unique marker BEFORE the generic specialist marker.
        ("VERIFICATION analyst", critic or [_text(_CHECKS_JSON)]),
        ("specialist in a portfolio deep-dive team", specialists or [_text("Finding.")] * 4),
        (DEEP_DIVE_SYNTHESIS_PROMPT[:60], synthesis or [_text(_REPORT_JSON)]),
    ]


async def _run(repo, uid, client, monkeypatch, on_event=None):
    monkeypatch.setattr(
        dd, "build_market_context", AsyncMock(return_value='{"positions": []}')
    )
    run_id = await repo.create_run(
        trigger="deep_dive",
        user_message="[portfolio deep dive]",
        model="claude-sonnet-4-6",
        prompt_version="test",
        user_id=uid,
    )
    report_id = await repo.create_deep_dive_report(run_id=run_id, user_id=uid)
    result = await dd.run_deep_dive(
        repo,
        user_id=uid,
        report_id=report_id,
        run_id=run_id,
        client=client,
        on_event=on_event,
    )
    return result, await repo.get_deep_dive_report(report_id), run_id


@pytest.fixture()
def repo_user():
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    return repo, uid


async def test_happy_path_completed_report(monkeypatch, repo_user):
    repo, uid = repo_user
    events: list[dict] = []

    async def on_event(ev):
        events.append(ev)

    result, row, run_id = await _run(
        repo, uid, RoutedClient(_routes()), monkeypatch, on_event
    )

    assert result["status"] == "completed"
    assert row.status == "completed"
    assert row.report["headline"] == "Portfolio holding up"
    assert row.report["schema_version"] == dd.REPORT_SCHEMA_VERSION
    assert row.report["verification_summary"] == {
        "checked": 2, "verified": 1, "challenged": 1,
    }
    assert row.report["failed_specialists"] == []
    assert row.summary == "Short summary for delivery."
    # Summary was handed to the delivery stack
    assert "Short summary for delivery." in repo.outbound
    # Anchor run finalized with accumulated cost (plan + 4 specialists +
    # critic + synthesis all recorded usage)
    run = repo.runs[run_id]
    assert run["status"] == "completed"
    assert run["cost_usd"] > 0
    # Progress snapshot fully advanced (rehydration source for the UI)
    assert row.progress["plan"] == "completed"
    assert row.progress["research"] == "completed"
    assert set(row.progress["specialists"].values()) == {"completed"}
    assert row.progress["synthesize"] == "completed"
    # Event stream told the same story
    stages = [(e["stage"], e["status"]) for e in events if e["type"] == "dd_stage"]
    assert ("plan", "started") == stages[0]
    assert ("synthesize", "completed") in stages
    assert events[-1]["type"] == "dd_done"


async def test_one_specialist_failure_degrades_to_partial(monkeypatch, repo_user):
    repo, uid = repo_user
    # First specialist call blows up; the other three answer.
    specialists = [RuntimeError("boom"), _text("Finding."), _text("Finding."), _text("Finding.")]
    result, row, _ = await _run(
        repo, uid, RoutedClient(_routes(specialists=specialists)), monkeypatch
    )
    assert result["status"] == "partial"
    assert row.status == "partial"
    assert len(row.report["failed_specialists"]) == 1
    assert "failed" in row.progress["specialists"].values()
    # Report still delivered
    assert row.summary


async def test_critic_garbage_yields_zero_checks_not_failure(monkeypatch, repo_user):
    repo, uid = repo_user
    result, row, _ = await _run(
        repo, uid,
        RoutedClient(_routes(critic=[_text("not json at all")])),
        monkeypatch,
    )
    assert result["status"] == "completed"
    assert row.report["verification_summary"] == {
        "checked": 0, "verified": 0, "challenged": 0,
    }


async def test_plan_garbage_falls_back_to_default_questions(monkeypatch, repo_user):
    repo, uid = repo_user
    plan = [_text("nope"), _text("still nope")]  # both plan attempts unparseable
    result, row, _ = await _run(
        repo, uid, RoutedClient(_routes(plan=plan)), monkeypatch
    )
    assert result["status"] == "completed"  # fallback questions kept it alive
    assert row.report["headline"] == "Portfolio holding up"


async def test_synthesis_garbage_falls_back_to_text_report(monkeypatch, repo_user):
    repo, uid = repo_user
    synthesis = [_text("prose, not json"), _text("more prose")]
    result, row, _ = await _run(
        repo, uid, RoutedClient(_routes(synthesis=synthesis)), monkeypatch
    )
    assert result["status"] in ("completed", "partial")
    assert row.report["overview"] == "more prose"
    assert row.report["sections"] == []
    assert row.summary == "more prose"


async def test_all_specialists_dead_is_an_error_report(monkeypatch, repo_user):
    repo, uid = repo_user
    specialists = [RuntimeError("boom")] * 4
    result, row, run_id = await _run(
        repo, uid, RoutedClient(_routes(specialists=specialists)), monkeypatch
    )
    assert result["status"] == "error"
    assert row.status == "error"
    assert repo.runs[run_id]["status"] == "error"
    assert repo.outbound == []  # nothing deliverable
