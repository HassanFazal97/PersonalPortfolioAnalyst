"""Deterministic evidence verification: the no-LLM numbers gate."""

from __future__ import annotations

from app.agent.picks.verify import verify_evidence

FACTS = {
    "forward_pe": {"value": 14.2, "sector_median": 21.0},
    "ev_to_ebitda": {"value": 9.8, "sector_median": 13.5},
    "roe_pct": {"value": 18.0, "sector_median": None},
}


def test_exact_match_passes_untouched():
    out, notes = verify_evidence(
        [{"metric": "forward_pe", "value": 14.2, "sector_median": 21.0}], FACTS
    )
    assert out == [{"metric": "forward_pe", "value": 14.2, "sector_median": 21.0}]
    assert notes == []


def test_rounding_within_tolerance_passes():
    out, notes = verify_evidence(
        [{"metric": "forward_pe", "value": 14.0, "sector_median": 21.2}], FACTS
    )
    assert notes == []
    # Canonical values are served either way.
    assert out[0]["value"] == 14.2


def test_drifted_value_is_repaired_to_fact_sheet():
    out, notes = verify_evidence(
        [{"metric": "ev_to_ebitda", "value": 15.0, "sector_median": 13.5}], FACTS
    )
    assert out[0]["value"] == 9.8
    assert out[0]["repaired"] is True
    assert any("repaired ev_to_ebitda" in n for n in notes)


def test_unknown_metric_is_dropped():
    out, notes = verify_evidence(
        [{"metric": "magic_ratio", "value": 1.0, "sector_median": 2.0}], FACTS
    )
    assert out == []
    assert any("unknown metric" in n for n in notes)


def test_hallucinated_median_is_repaired():
    out, _ = verify_evidence(
        [{"metric": "forward_pe", "value": 14.2, "sector_median": 99.0}], FACTS
    )
    assert out[0]["sector_median"] == 21.0
    assert out[0]["repaired"] is True


def test_missing_median_in_facts_is_fine():
    out, notes = verify_evidence(
        [{"metric": "roe_pct", "value": 18.0}], FACTS
    )
    assert out[0]["sector_median"] is None
    assert notes == []


def test_garbage_shapes_are_ignored():
    out, notes = verify_evidence(
        ["not a dict", {"no_metric": True}, None], FACTS
    )
    assert out == []
