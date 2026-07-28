"""Investor profile: the personalization layer (migration 022).

Traits captured during onboarding (horizon, risk tolerance, experience,
goals) are the source of truth; the archetype is a label derived from them
and used for prompt guidance and UI copy. Users who skip profiling get
``DEFAULT_PROFILE`` — a balanced long-term baseline whose knob values keep
every pipeline behaving exactly as it did before profiles existed.

Only the enumerated values below ever reach LLM prompts — profiling asks no
free-text questions, so this module doubles as the prompt-injection guard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ARCHETYPES = ("day_trader", "swing_trader", "long_term_growth", "income_preservation")
HORIZONS = ("days", "weeks_months", "years", "decade_plus")
EXPERIENCE_LEVELS = ("new", "lt_1y", "1_5y", "5_10y", "10y_plus")
GOALS = (
    "grow_long_term",
    "income",
    "preserve_capital",
    "short_term_gains",
    "retirement",
    "big_purchase",
)

# Risk-comfort postures shown in the onboarding Monte Carlo picker. The k
# multiplier scales portfolio volatility in the projections; the mapped risk
# tolerance applies when the user picks that posture ('current' keeps the
# answer-derived value).
POSTURES: dict[str, dict[str, Any]] = {
    "defensive": {"k": 0.6, "risk_tolerance": 3, "label": "A smoother ride"},
    "current": {"k": 1.0, "risk_tolerance": None, "label": "Your current mix"},
    "aggressive": {"k": 1.5, "risk_tolerance": 8, "label": "Higher octane"},
}

ARCHETYPE_LABELS = {
    "day_trader": "Day Trader",
    "swing_trader": "Swing Trader",
    "long_term_growth": "Long-Term Growth",
    "income_preservation": "Income & Preservation",
}


@dataclass(frozen=True)
class InvestorProfile:
    archetype: str
    risk_tolerance: int
    horizon: str
    experience: str | None
    goals: tuple[str, ...]
    is_default: bool = False


DEFAULT_PROFILE = InvestorProfile(
    archetype="long_term_growth",
    risk_tolerance=5,
    horizon="years",
    experience=None,
    goals=(),
    is_default=True,
)


def derive_archetype(
    horizon: str | None, risk_tolerance: int | None, goals: list[str] | tuple[str, ...]
) -> str:
    """Deterministic answers→archetype mapping. Traits drive behavior, so
    boundary cases resolving to a neighboring label is harmless."""
    goals = set(goals or ())
    if horizon == "days":
        return "day_trader"
    if horizon == "weeks_months" or "short_term_gains" in goals:
        return "swing_trader"
    if goals & {"income", "preserve_capital"} and (risk_tolerance or 5) <= 4:
        return "income_preservation"
    return "long_term_growth"


def profile_from_user(user: Any | None) -> InvestorProfile:
    """The single entry point every pipeline uses to resolve a profile.

    NULL archetype (never profiled, or skipped) yields ``DEFAULT_PROFILE``."""
    archetype = getattr(user, "investor_archetype", None) if user is not None else None
    if archetype not in ARCHETYPES:
        return DEFAULT_PROFILE
    risk = getattr(user, "risk_tolerance", None) or DEFAULT_PROFILE.risk_tolerance
    horizon = getattr(user, "investing_horizon", None)
    if horizon not in HORIZONS:
        horizon = DEFAULT_PROFILE.horizon
    experience = getattr(user, "investing_experience", None)
    if experience not in EXPERIENCE_LEVELS:
        experience = None
    raw_goals = getattr(user, "investing_goals", None) or []
    goals = tuple(g for g in raw_goals if g in GOALS)
    return InvestorProfile(
        archetype=archetype,
        risk_tolerance=int(risk),
        horizon=horizon,
        experience=experience,
        goals=goals,
    )


# ---- personalization knobs -------------------------------------------------
# The default profile intentionally reproduces pre-profile behavior bit-exact
# (7-day window, 1.0x thresholds) so un-profiled users see no change.


def digest_window_days(profile: InvestorProfile) -> int:
    """Price-history window for the digest's market context."""
    if profile.is_default:
        return 7
    return {
        "day_trader": 2,
        "swing_trader": 7,
        "long_term_growth": 30,
        "income_preservation": 30,
    }[profile.archetype]


def mover_threshold_multiplier(profile: InvestorProfile) -> float:
    """Scales ``digest_mover_threshold_pct``: traders care about smaller
    moves, preservation-minded investors only about larger ones."""
    if profile.is_default:
        return 1.0
    return {
        "day_trader": 0.5,
        "swing_trader": 0.75,
        "long_term_growth": 1.0,
        "income_preservation": 1.25,
    }[profile.archetype]


def news_min_salience(profile: InvestorProfile, base: float) -> float:
    """Per-profile salience floor for persisting classified news: traders
    want a wider net, long-horizon investors a quieter feed."""
    if profile.is_default:
        return base
    delta = {
        "day_trader": -0.1,
        "swing_trader": -0.1,
        "long_term_growth": 0.1,
        "income_preservation": 0.1,
    }[profile.archetype]
    return min(1.0, max(0.0, base + delta))


def anomaly_severity_multiplier(profile: InvestorProfile) -> float:
    """Per-user alert-worthiness floor scaling — detector calibration stays
    global; this only gates which already-flagged anomalies become alerts for
    this user. Never below 1.0: the global scan already applied the base
    floor, so a lower per-user floor could not surface anything new. Long-
    horizon investors get a quieter feed (only stronger anomalies interrupt)."""
    if profile.is_default:
        return 1.0
    return {
        "day_trader": 1.0,
        "swing_trader": 1.0,
        "long_term_growth": 1.2,
        "income_preservation": 1.1,
    }[profile.archetype]


def resolve_risk_tolerance(
    explicit: int | None, chosen_posture: str | None
) -> int:
    """PUT /me/profile risk resolution: explicit slider value wins, else the
    picked posture's mapping, else the balanced default."""
    if explicit is not None:
        return explicit
    if chosen_posture is not None:
        mapped = POSTURES.get(chosen_posture, {}).get("risk_tolerance")
        if mapped is not None:
            return mapped
    return DEFAULT_PROFILE.risk_tolerance


# ---- prompt composition ------------------------------------------------------
# Text constants live in app/agent/prompts.py (the module rule); these helpers
# only fill them in. Only enum-derived values are interpolated — never free text.

_HORIZON_PHRASES = {
    "days": "acts within days",
    "weeks_months": "acts over weeks to months",
    "years": "holds for years",
    "decade_plus": "thinks in decades",
}
_EXPERIENCE_PHRASES = {
    "new": "new to investing",
    "lt_1y": "under a year of experience",
    "1_5y": "1-5 years of experience",
    "5_10y": "5-10 years of experience",
    "10y_plus": "10+ years of experience",
}
_GOAL_PHRASES = {
    "grow_long_term": "long-term growth",
    "income": "income",
    "preserve_capital": "capital preservation",
    "short_term_gains": "short-term gains",
    "retirement": "retirement",
    "big_purchase": "a major purchase",
}


def build_profile_context(profile: InvestorProfile) -> str:
    """The <investor_profile> block appended to system prompts. Always at the
    END of the prompt (after any user-context block) so shared static prefixes
    stay cacheable."""
    from app.agent import prompts

    if profile.is_default:
        return prompts.INVESTOR_PROFILE_DEFAULT_CONTEXT
    experience_clause = (
        f", {_EXPERIENCE_PHRASES[profile.experience]}" if profile.experience else ""
    )
    goal_words = [_GOAL_PHRASES[g] for g in profile.goals]
    goals_clause = f", investing for {', '.join(goal_words)}" if goal_words else ""
    return prompts.INVESTOR_PROFILE_TEMPLATE.format(
        archetype_label=ARCHETYPE_LABELS[profile.archetype],
        horizon=_HORIZON_PHRASES[profile.horizon],
        risk_tolerance=profile.risk_tolerance,
        experience_clause=experience_clause,
        goals_clause=goals_clause,
        guidance=prompts.ARCHETYPE_GUIDANCE[profile.archetype],
    )


def plan_profile_suffix(profile: InvestorProfile) -> str:
    """Digest-planner prioritization override; empty for the default profile
    (the base PLAN_SYSTEM_PROMPT ordering is the baseline)."""
    from app.agent import prompts

    if profile.is_default:
        return ""
    return prompts.PLAN_PROFILE_SUFFIX_BY_ARCHETYPE[profile.archetype]


def synthesize_profile_suffix(profile: InvestorProfile) -> str:
    """Framing block appended to the digest synthesizer's system prompt. Tone
    and emphasis only — it restates that the format contract is unchanged."""
    return (
        "\n"
        + build_profile_context(profile)
        + "\nThis profile shifts emphasis and tone only — every format rule "
        "above (section labels, ordering, length caps) is unchanged."
    )


def profile_payload(user: Any | None) -> dict[str, Any]:
    """The ``profile`` block in ``/me`` responses."""
    profile = profile_from_user(user)
    completed = (
        getattr(user, "profile_completed_at", None) is not None
        if user is not None
        else False
    )
    dismissed = (
        getattr(user, "profile_prompt_dismissed_at", None) is not None
        if user is not None
        else False
    )
    return {
        "archetype": profile.archetype,
        "archetype_label": ARCHETYPE_LABELS[profile.archetype],
        "risk_tolerance": profile.risk_tolerance,
        "horizon": profile.horizon,
        "experience": profile.experience,
        "goals": list(profile.goals),
        "completed": completed,
        "prompt_dismissed": dismissed,
        "is_default": profile.is_default,
    }
