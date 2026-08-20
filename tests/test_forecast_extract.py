"""Extractor parsing/validation: the Python gate, not the model, decides."""

from __future__ import annotations

from app.agent.forecasts.extract import parse_extraction, validate_claims

SOURCE = (
    "Your portfolio gained 2% this week. NVDA could drop 10%+ if guidance "
    "disappoints at earnings. We expect SHOP.TO to outperform the index over "
    "the next quarter. The shop on the corner is irrelevant."
)


def _claim(**overrides):
    base = {
        "claim_text": "NVDA could drop 10%+ if guidance disappoints at earnings.",
        "claim_type": "direction",
        "tickers": ["NVDA"],
        "direction": "down",
        "horizon": "1m",
        "magnitude_min_pct": 10,
        "confidence_verbal": "low",
    }
    base.update(overrides)
    return base


def test_valid_claim_accepted_with_horizon_and_magnitude():
    claims, drops = validate_claims({"claims": [_claim()]}, SOURCE)
    assert len(claims) == 1
    c = claims[0]
    assert c["horizon_days"] == 30 and c["magnitude_min_pct"] == 10.0
    assert c["tickers"] == ["NVDA"] and c["direction"] == "down"
    assert drops["not_verbatim"] == 0


def test_paraphrased_claim_dropped():
    fake = _claim(claim_text="NVDA might fall over ten percent after earnings.")
    claims, drops = validate_claims({"claims": [fake]}, SOURCE)
    assert claims == [] and drops["not_verbatim"] == 1


def test_whitespace_normalization_still_verbatim():
    wrapped = _claim(
        claim_text="NVDA could drop 10%+ if\n  guidance disappoints at earnings."
    )
    claims, _ = validate_claims({"claims": [wrapped]}, SOURCE)
    assert len(claims) == 1


def test_unknown_ticker_dropped_but_claim_kept():
    claims, _ = validate_claims({"claims": [_claim(tickers=["NVDA", "TSLA"])]}, SOURCE)
    assert claims[0]["tickers"] == ["NVDA"]


def test_ticker_word_boundary():
    # "shop" prose and "SHOP" inside SHOP.TO must not create a bare SHOP match.
    claims, _ = validate_claims(
        {"claims": [_claim(tickers=["SHOP", "SHOP.TO"])]}, SOURCE
    )
    assert claims[0]["tickers"] == ["SHOP.TO"]


def test_bad_enums_and_shapes_dropped():
    claims, drops = validate_claims(
        {"claims": [_claim(claim_type="prophecy"), _claim(direction="sideways"), 42]},
        SOURCE,
    )
    assert claims == []
    assert drops["bad_enum"] == 2 and drops["bad_shape"] == 1


def test_unstated_horizon_and_null_direction():
    c = _claim(horizon="unstated", direction="null", claim_type="risk_warning")
    claims, _ = validate_claims({"claims": [c]}, SOURCE)
    assert claims[0]["horizon_days"] is None and claims[0]["direction"] is None


def test_parse_extraction_garbage_and_fences():
    assert parse_extraction("not json at all", SOURCE) == ([], {"parse_error": 1})
    fenced = '```json\n{"claims": []}\n```'
    claims, drops = parse_extraction(fenced, SOURCE)
    assert claims == [] and drops.get("parse_error") is None
