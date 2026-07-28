"""Unit tests for the investor-profile layer (app/profile.py) and its
threading into the digest pipeline's context builder."""

import uuid
from types import SimpleNamespace

import pytest

import app.agent.digest_pipeline as dp
from app.config import get_settings
from app.profile import (
    ARCHETYPES,
    DEFAULT_PROFILE,
    InvestorProfile,
    anomaly_severity_multiplier,
    build_profile_context,
    derive_archetype,
    digest_window_days,
    mover_threshold_multiplier,
    news_min_salience,
    plan_profile_suffix,
    profile_from_user,
    profile_payload,
    resolve_risk_tolerance,
    synthesize_profile_suffix,
)
from app.tools.registry import ToolContext
from tests.fakes import FakeRepo

# ---- archetype derivation ----------------------------------------------------


@pytest.mark.parametrize(
    ("horizon", "risk", "goals", "expected"),
    [
        ("days", 9, [], "day_trader"),
        ("days", 2, ["income"], "day_trader"),  # horizon 'days' wins outright
        ("weeks_months", 5, [], "swing_trader"),
        ("years", 7, ["short_term_gains"], "swing_trader"),
        ("years", 3, ["income"], "income_preservation"),
        ("years", 4, ["preserve_capital", "retirement"], "income_preservation"),
        ("years", 5, ["income"], "long_term_growth"),  # risk 5 > threshold 4
        ("years", 8, [], "long_term_growth"),
        ("decade_plus", 5, ["retirement"], "long_term_growth"),
        (None, None, [], "long_term_growth"),
    ],
)
def test_derive_archetype(horizon, risk, goals, expected):
    assert derive_archetype(horizon, risk, goals) == expected


def test_resolve_risk_tolerance():
    assert resolve_risk_tolerance(7, "defensive") == 7  # explicit wins
    assert resolve_risk_tolerance(None, "defensive") == 3
    assert resolve_risk_tolerance(None, "aggressive") == 8
    # 'current' has no mapped value -> balanced default
    assert resolve_risk_tolerance(None, "current") == 5
    assert resolve_risk_tolerance(None, None) == 5


# ---- profile_from_user ---------------------------------------------------------


def test_profile_from_user_defaults():
    assert profile_from_user(None) is DEFAULT_PROFILE
    # Un-profiled row (all NULLs) -> default
    user = SimpleNamespace(investor_archetype=None)
    assert profile_from_user(user) is DEFAULT_PROFILE
    # Garbage archetype -> default, never a KeyError downstream
    user = SimpleNamespace(investor_archetype="yolo_trader")
    assert profile_from_user(user) is DEFAULT_PROFILE


def test_profile_from_user_reads_traits():
    user = SimpleNamespace(
        investor_archetype="day_trader",
        risk_tolerance=8,
        investing_horizon="days",
        investing_experience="1_5y",
        investing_goals=["short_term_gains", "not_a_goal"],
    )
    p = profile_from_user(user)
    assert p.archetype == "day_trader"
    assert p.risk_tolerance == 8
    assert p.horizon == "days"
    assert p.experience == "1_5y"
    assert p.goals == ("short_term_gains",)  # unknown values filtered
    assert p.is_default is False


# ---- knobs: default profile must reproduce pre-profile behavior ----------------


def test_default_profile_knobs_are_neutral():
    assert digest_window_days(DEFAULT_PROFILE) == 7
    assert mover_threshold_multiplier(DEFAULT_PROFILE) == 1.0
    assert news_min_salience(DEFAULT_PROFILE, 0.55) == 0.55
    assert anomaly_severity_multiplier(DEFAULT_PROFILE) == 1.0
    assert plan_profile_suffix(DEFAULT_PROFILE) == ""


@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_knobs_cover_every_archetype(archetype):
    p = InvestorProfile(archetype, 5, "years", None, ())
    assert digest_window_days(p) > 0
    assert mover_threshold_multiplier(p) > 0
    assert 0.0 <= news_min_salience(p, 0.55) <= 1.0
    assert anomaly_severity_multiplier(p) >= 1.0  # scan floor already gates
    assert plan_profile_suffix(p)
    assert build_profile_context(p)


def test_news_min_salience_clamps():
    trader = InvestorProfile("day_trader", 8, "days", None, ())
    saver = InvestorProfile("income_preservation", 3, "years", None, ("income",))
    assert news_min_salience(trader, 0.05) == 0.0
    assert news_min_salience(saver, 0.95) == 1.0
    assert news_min_salience(trader, 0.55) < 0.55 < news_min_salience(saver, 0.55)


# ---- prompt composition ---------------------------------------------------------


def test_build_profile_context_contents():
    p = InvestorProfile("income_preservation", 3, "years", "10y_plus", ("income",))
    block = build_profile_context(p)
    assert block.startswith("\n<investor_profile>")
    assert "Income & Preservation" in block
    assert "3/10" in block
    assert "10+ years of experience" in block
    assert "buy or sell" in block


def test_default_context_is_leaner_but_present():
    block = build_profile_context(DEFAULT_PROFILE)
    assert "<investor_profile>" in block
    assert "not set an investor profile" in block


def test_synthesize_suffix_restates_format_contract():
    p = InvestorProfile("day_trader", 8, "days", None, ())
    suffix = synthesize_profile_suffix(p)
    assert "<investor_profile>" in suffix
    assert "format rule" in suffix


# ---- payload -------------------------------------------------------------------


def test_profile_payload_shapes():
    unset = profile_payload(None)
    assert unset["is_default"] is True
    assert unset["completed"] is False
    assert unset["archetype"] == "long_term_growth"

    user = SimpleNamespace(
        investor_archetype="swing_trader",
        risk_tolerance=6,
        investing_horizon="weeks_months",
        investing_experience=None,
        investing_goals=["short_term_gains"],
        profile_completed_at="2026-07-28T00:00:00Z",
        profile_prompt_dismissed_at=None,
    )
    got = profile_payload(user)
    assert got["archetype"] == "swing_trader"
    assert got["archetype_label"] == "Swing Trader"
    assert got["completed"] is True
    assert got["prompt_dismissed"] is False
    assert got["is_default"] is False


# ---- digest pipeline threading --------------------------------------------------


@pytest.mark.asyncio
async def test_build_market_context_uses_profile_window(monkeypatch):
    uid = uuid.uuid4()
    repo = FakeRepo()
    seen_days: list[int] = []

    async def fake_get_portfolio(payload, ctx):
        return {
            "positions": [{"ticker": "NVDA", "quantity": 1, "market_value": 100}],
            "totals": {},
        }

    async def fake_history(payload, ctx):
        seen_days.append(payload["days"])
        return {"period_return_pct": 1.0}

    monkeypatch.setattr(dp.portfolio, "get_portfolio", fake_get_portfolio)
    monkeypatch.setattr(dp.market, "get_price_history", fake_history)

    ctx = ToolContext(settings=get_settings(), repo=repo, user_id=uid)
    raw = await dp.build_market_context(
        ctx, tz="America/Toronto", plan="pro", digest_tickers=[], window_days=2
    )
    import json

    data = json.loads(raw)
    assert seen_days == [2]
    assert data["period_days"] == 2
    assert data["period_return_pct_by_ticker"] == {"NVDA": 1.0}


def test_holdings_scaffold_threshold_and_label():
    positions = [
        {"ticker": "NVDA", "last_price": 100.0, "day_change_pct": -1.5,
         "quantity": 1, "market_value": 100, "unrealized_pnl": None},
        {"ticker": "AAPL", "last_price": 200.0, "day_change_pct": -0.5,
         "quantity": 1, "market_value": 200, "unrealized_pnl": None},
    ]
    settings = get_settings()
    # Default threshold (2.0): neither name is detailed.
    base = dp.build_holdings_scaffold(
        positions, {}, news_tickers=set(), settings=settings
    )
    assert "no holding moved materially" in base
    # A day trader's halved threshold (1.0) pulls NVDA into DETAILED, and the
    # 2-day window relabels the period column.
    tuned = dp.build_holdings_scaffold(
        positions,
        {"NVDA": -3.0},
        news_tickers=set(),
        settings=settings,
        mover_threshold=1.0,
        period_days=2,
    )
    assert "NVDA" in tuned.split("QUIET")[0]
    assert "2d" in tuned
