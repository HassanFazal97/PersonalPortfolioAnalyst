"""Best Stocks pipeline: stage flow, verification, degradation, persistence."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta

import pytest

import app.agent.picks.pipeline as pp
from tests.fakes import FakeRepo

AS_OF = date(2026, 7, 24)

_ANALYSIS_JSON = json.dumps(
    {
        "ticker": "CHEAP",
        "thesis": "Trades well below sector multiples with stable margins.",
        "why_now": "Guidance raised on July 20.",
        "valuation_evidence": [
            {"metric": "forward_pe", "value": 7.0, "sector_median": 26.0}
        ],
        "risks": [
            {"text": "Customer concentration.", "severity": "medium"},
            {"text": "Cyclical end markets.", "severity": "high"},
        ],
        "catalysts": ["Earnings Aug 12"],
        "model_confidence": "high",
        "data_gaps": [],
    }
)

_CHECKS_JSON = json.dumps(
    {
        "checks": [
            {
                "ticker": "CHEAP",
                "claim": "Guidance raised on July 20",
                "verdict": "verified",
                "note": "matches news",
            }
        ]
    }
)

_MOVER_JSON = json.dumps(
    {
        "ticker": "JUMP",
        "why": "Beat earnings on July 23.",
        "news_grounded": True,
        "sources": ["Reuters"],
    }
)

_OVERVIEW_JSON = json.dumps(
    {"headline": "Value in industrials", "overview": "Para one.\nPara two."}
)


def _text(text):
    return {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 200, "output_tokens": 50},
    }


class RoutedClient:
    """Routes canned responses by system-prompt marker (deep-dive test twin)."""

    def __init__(self, routes):
        self._routes = [(m, list(rs)) for m, rs in routes]
        self.calls = []

    @property
    def messages(self):
        return self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        system = kwargs.get("system", "")
        if isinstance(system, list):
            system = "".join(b.get("text", "") for b in system)
        for marker, responses in self._routes:
            if marker in system and responses:
                resp = responses.pop(0)
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"no scripted route for system prompt: {system[:80]}...")


def _routes(*, analysts=None, critic=None, movers=None, synthesis=None, n_analysts=2):
    def default_analysis(t):
        d = json.loads(_ANALYSIS_JSON)
        d["ticker"] = t
        return _text(json.dumps(d))

    return [
        ("adversarial VERIFICATION analyst", critic or [_text(_CHECKS_JSON)]),
        ("explain one notable stock move", movers or [_text(_MOVER_JSON)] * 3),
        ("equity analyst in a stock-screening team",
         analysts if analysts is not None else [default_analysis("X")] * n_analysts),
        ("market-overview header", synthesis or [_text(_OVERVIEW_JSON)]),
    ]


class _Settings:
    """Minimal settings double for the pipeline (bypasses get_settings)."""

    model = "claude-sonnet-4-6"
    classifier_model = "claude-haiku-4-5"
    anthropic_api_key = "test"
    picks_max_iterations = 120
    picks_max_cost_usd = 5.0
    picks_top_candidates = 2
    picks_final_count = 10
    picks_max_movers = 3
    picks_history_days = 420
    picks_universe_limit = 0
    tz = "America/Toronto"


def _closes(n=300, last_jump=None, seed=1.0):
    rows, price, x = [], 100.0, seed
    d = AS_OF - timedelta(days=int(n * 1.5))
    while len(rows) < n:
        if d.weekday() < 5:
            x = math.sin(x * 12.9898 + 78.233) * 43758.5453
            noise = (x - math.floor(x)) * 2 - 1
            r = 0.0004 + 0.012 * noise
            if last_jump is not None and len(rows) == n - 1:
                r = last_jump
            price *= math.exp(r)
            rows.append({"date": d.isoformat(), "adj_close": round(price, 4)})
        d += timedelta(days=1)
    rows[-1]["date"] = AS_OF.isoformat()
    return rows


def _fund(fpe=20.0):
    return {
        "quote_type": "EQUITY",
        "profile": {"name": "TestCo", "sector": "Technology", "market_cap": 5e10},
        "valuation": {
            "trailing_pe": fpe * 1.1, "forward_pe": fpe, "price_to_sales": 3.0,
            "price_to_book": 4.0, "ev_to_ebitda": 15.0, "price_to_fcf": 22.0,
            "peg": 1.5,
        },
        "growth": {"revenue_growth_pct": 8.0, "earnings_growth_pct": 10.0},
        "profitability": {
            "gross_margin_pct": 50.0, "operating_margin_pct": 25.0,
            "net_margin_pct": 18.0, "roe_pct": 20.0,
        },
        "financial_health": {"debt_to_equity": 0.8, "current_ratio": 1.5},
        "price_action": {
            "beta": 1.0, "analyst_target": 130.0, "analyst_count": 10,
            "short_pct_of_float": 1.5, "high_52w": 140.0,
        },
    }


@pytest.fixture()
async def seeded_repo(monkeypatch):
    """FakeRepo with a 10-name universe stored: 9 ordinary + 1 cheap + 1 mover."""
    repo = FakeRepo()
    tickers = [f"T{i:02d}" for i in range(8)] + ["CHEAP", "JUMP"]
    monkeypatch.setattr(pp, "get_universe", lambda limit=0: tickers)
    monkeypatch.setattr(pp, "get_settings", lambda: _Settings())
    for i, t in enumerate(tickers):
        fpe = 7.0 if t == "CHEAP" else 22.0 + i
        await repo.upsert_ticker_fundamentals(
            ticker=t, quote_type="EQUITY", data=_fund(fpe)
        )
        await repo.upsert_daily_prices(
            t, _closes(seed=1.0 + i, last_jump=0.12 if t == "JUMP" else None)
        )

    async def fake_news(payload, ctx):
        return {"items": [{"headline": "Beat earnings", "source": "Reuters"}]}

    monkeypatch.setattr(pp.news, "search_news", fake_news)
    return repo


def test_lenient_parse_survives_prose_prefix():
    wrapped = "Here is the analysis you asked for:\n" + _ANALYSIS_JSON + "\nHope this helps."
    parsed = pp.parse_analysis(wrapped)
    assert parsed is not None and parsed["ticker"] == "CHEAP"
    assert pp.parse_analysis("no json here at all") is None
    # Braces inside strings don't break the extractor.
    tricky = 'preamble {"thesis": "a {brace} inside", "x": "y"} trailer'
    assert pp.parse_analysis(tricky)["thesis"] == "a {brace} inside"


async def test_happy_path_completed_run(seeded_repo):
    repo = seeded_repo
    client = RoutedClient(_routes())
    result = await pp.run_stock_picks(repo, client=client, run_date=AS_OF)

    assert result["status"] == "completed"
    row = await repo.get_latest_picks_run()
    assert row is not None and row.status == "completed"
    payload = row.payload
    assert payload["as_of"] == AS_OF.isoformat()
    assert payload["headline"] == "Value in industrials"
    assert payload["disclaimer"]
    # CHEAP is the top pick with the analyst thesis attached.
    top = payload["picks"][0]
    assert top["ticker"] == "CHEAP"
    assert top["analysis"] == "ok"
    assert top["thesis"].startswith("Trades well below")
    # Deterministic verification kept the honest evidence entry.
    assert top["valuation_evidence"][0]["metric"] == "forward_pe"
    assert top["valuation_evidence"][0]["value"] == 7.0
    # Confidence is computed and bounded.
    assert 0.0 < top["confidence"] <= 1.0
    # The mover got a grounded explanation.
    jump = next(m for m in payload["movers"] if m["ticker"] == "JUMP")
    assert jump["news_grounded"] is True
    assert "Beat earnings" in jump["why"]
    # Track record entries persisted with a frozen entry price.
    entries = await repo.list_pick_entries(since=AS_OF)
    assert len(entries) == len(payload["picks"])
    assert all(e.entry_price for e in entries)
    # Anchor run finalized with accumulated cost.
    run = repo.runs[row.run_id]
    assert run["status"] == "completed"
    assert run["cost_usd"] > 0


async def test_hallucinated_evidence_is_repaired(seeded_repo):
    repo = seeded_repo
    bad = json.loads(_ANALYSIS_JSON)
    bad["valuation_evidence"] = [
        {"metric": "forward_pe", "value": 3.0, "sector_median": 50.0},
        {"metric": "made_up_metric", "value": 1.0},
    ]
    analysts = [_text(json.dumps(bad))] * 2
    client = RoutedClient(_routes(analysts=analysts))
    await pp.run_stock_picks(repo, client=client, run_date=AS_OF)

    row = await repo.get_latest_picks_run()
    top = row.payload["picks"][0]
    ev = top["valuation_evidence"]
    # The invented metric is gone; the drifted value snapped to the fact sheet.
    assert len(ev) == 1
    assert ev[0]["metric"] == "forward_pe"
    assert ev[0]["value"] == 7.0  # CHEAP's true forward P/E
    assert ev[0].get("repaired") is True
    assert row.payload["verification_summary"]["evidence_repaired"] >= 1


async def test_failed_analyst_degrades_to_quant_only_partial(seeded_repo):
    repo = seeded_repo
    analysts = [RuntimeError("boom"), _text(_ANALYSIS_JSON)]
    client = RoutedClient(_routes(analysts=analysts))
    result = await pp.run_stock_picks(repo, client=client, run_date=AS_OF)

    assert result["status"] == "partial"
    row = await repo.get_latest_picks_run(statuses=("partial",))
    picks = row.payload["picks"]
    assert len(picks) == 2
    kinds = {p["analysis"] for p in picks}
    assert kinds == {"ok", "unavailable"}
    quant_only = next(p for p in picks if p["analysis"] == "unavailable")
    assert quant_only["composite"] is not None
    assert quant_only["confidence"] <= pp.CONFIDENCE_GAP_CAP


async def test_dead_critic_leaves_claims_unverified(seeded_repo):
    repo = seeded_repo
    client = RoutedClient(_routes(critic=[RuntimeError("dead critic")]))
    result = await pp.run_stock_picks(repo, client=client, run_date=AS_OF)

    assert result["status"] == "partial"
    row = await repo.get_latest_picks_run(statuses=("partial",))
    assert row.payload["verification_summary"]["critic_ran"] is False
    assert all(
        p["verification"]["critic_ran"] is False for p in row.payload["picks"]
    )


async def test_challenged_pick_is_demoted(seeded_repo):
    repo = seeded_repo
    checks = {
        "checks": [
            {"ticker": "CHEAP", "claim": "a", "verdict": "challenged", "note": "wrong"},
            {"ticker": "CHEAP", "claim": "b", "verdict": "challenged", "note": "wrong"},
        ]
    }
    client = RoutedClient(_routes(critic=[_text(json.dumps(checks))]))
    await pp.run_stock_picks(repo, client=client, run_date=AS_OF)

    row = await repo.get_latest_picks_run()
    picks = row.payload["picks"]
    # CHEAP screens #1 but sorts last after two challenged claims.
    assert picks[-1]["ticker"] == "CHEAP"
    assert picks[-1]["demoted"] is True
    assert picks[0]["demoted"] is False


async def test_stale_store_refuses_to_rank(monkeypatch, seeded_repo):
    repo = seeded_repo
    # Rerun dated far past the stored bars: everything fails the freshness gate.
    client = RoutedClient(_routes())
    result = await pp.run_stock_picks(
        repo, client=client, run_date=AS_OF + timedelta(days=30)
    )
    assert result["status"] == "error"
    row = await repo.get_latest_picks_run(statuses=("error",))
    assert row.payload is None
    assert row.stats["note"] == "stale data"
    # No LLM calls were spent on garbage data.
    assert client.calls == []


async def test_budget_cutoff_stops_admitting_analysts(seeded_repo, monkeypatch):
    repo = seeded_repo

    class TinyBudgetSettings(_Settings):
        picks_max_cost_usd = 0.0  # admission cutoff already reached at $0

    monkeypatch.setattr(pp, "get_settings", lambda: TinyBudgetSettings())
    # With admission blocked, no analyst or critic route is ever consumed;
    # movers and synthesis still run.
    client = RoutedClient(_routes(analysts=[], critic=[]))
    result = await pp.run_stock_picks(repo, client=client, run_date=AS_OF)

    assert result["status"] == "partial"
    row = await repo.get_latest_picks_run(statuses=("partial",))
    assert all(p["analysis"] == "unavailable" for p in row.payload["picks"])
    assert row.stats["skipped_for_budget"]
