"""Haiku extraction of forecasts from prose sources (digest bodies,
deep-dive free-text findings).

One cheap batched call per document (the ``classify.py`` pattern: strict-JSON
prompt, tolerant parse, safe coercion). The model only *finds and types*
claims — every number and every acceptance decision is Python's:

- ``claim_text`` must be a verbatim substring of the source (whitespace-
  normalized) or the claim is dropped — the anti-hallucination gate.
- Tickers not present in the source are dropped; a claim left with no valid
  tickers survives only as a market-level claim if it had none to begin with.
- Horizons snap to the allowed set; enums coerce or the claim is dropped.

Dropped counts are returned so the ledger job's stats make extraction loss
visible rather than silent.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.prompts import FORECAST_EXTRACT_PROMPT, FORECAST_EXTRACTOR_VERSION

_VALID_CLAIM_TYPES = frozenset(
    {"direction", "relative_performance", "risk_warning", "event", "volatility"}
)
_VALID_DIRECTIONS = frozenset({"up", "down", "flat", "outperform", "underperform"})
_VALID_CONFIDENCE = frozenset({"high", "medium", "low", "speculative"})
_HORIZON_MAP = {"1w": 7, "1m": 30, "3m": 91, "6m": 182, "unstated": None}
_MAX_CLAIMS_PER_DOC = 12
_MAX_DOC_CHARS = 20_000


def _normalize_ws(text: str) -> str:
    return " ".join(text.split())


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def _ticker_in_source(ticker: str, source_text: str) -> bool:
    """Word-boundary, case-sensitive match — 'SHOP' must not match
    'Shopify', the word 'shop', or the prefix of 'SHOP.TO' (a dot followed
    by an alphanumeric continues the symbol; a sentence-final dot does not).
    """
    if not ticker or not ticker.isupper():
        return False
    pattern = rf"(?<![A-Z0-9.]){re.escape(ticker)}(?!\.?[A-Z0-9])"
    return re.search(pattern, source_text) is not None


def validate_claims(
    raw: Any, source_text: str
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Coerce raw model output into accepted claim dicts + drop counters."""
    drops = {"not_verbatim": 0, "bad_enum": 0, "bad_shape": 0, "over_cap": 0}
    accepted: list[dict[str, Any]] = []
    rows = raw.get("claims") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        return [], drops
    normalized_source = _normalize_ws(source_text)
    for row in rows:
        if len(accepted) >= _MAX_CLAIMS_PER_DOC:
            drops["over_cap"] += 1
            continue
        if not isinstance(row, dict):
            drops["bad_shape"] += 1
            continue
        claim_text = str(row.get("claim_text") or "").strip()
        if not claim_text or _normalize_ws(claim_text) not in normalized_source:
            drops["not_verbatim"] += 1
            continue
        claim_type = row.get("claim_type")
        confidence = row.get("confidence_verbal")
        if claim_type not in _VALID_CLAIM_TYPES or confidence not in _VALID_CONFIDENCE:
            drops["bad_enum"] += 1
            continue
        direction = row.get("direction")
        if direction in (None, "null", ""):
            direction = None
        elif direction not in _VALID_DIRECTIONS:
            drops["bad_enum"] += 1
            continue
        horizon_days = _HORIZON_MAP.get(row.get("horizon"), None)
        tickers = [
            t
            for t in (row.get("tickers") or [])
            if isinstance(t, str) and _ticker_in_source(t, source_text)
        ]
        magnitude = row.get("magnitude_min_pct")
        try:
            magnitude = float(magnitude) if magnitude is not None else None
        except (TypeError, ValueError):
            magnitude = None
        accepted.append(
            {
                "claim_text": claim_text,
                "claim_type": claim_type,
                "tickers": tickers,
                "direction": direction,
                "horizon_days": horizon_days,
                "magnitude_min_pct": magnitude,
                "confidence_verbal": confidence,
            }
        )
    return accepted, drops


def parse_extraction(text: str, source_text: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    try:
        data = json.loads(_strip_fences(text))
    except (json.JSONDecodeError, TypeError):
        return [], {"parse_error": 1}
    return validate_claims(data, source_text)


async def extract_claims(
    client: Any, model: str, source_text: str
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, Any], dict[str, Any]]:
    """One Haiku call over one document. Returns (claims, drops, usage, log)."""
    doc = source_text[:_MAX_DOC_CHARS]
    messages = [{"role": "user", "content": doc}]
    response = await client.messages.create(
        model=model,
        max_tokens=2048,
        system=FORECAST_EXTRACT_PROMPT,
        messages=messages,
    )
    parts = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    text = "\n".join(parts).strip()
    claims, drops = parse_extraction(text, doc)
    usage_obj = getattr(response, "usage", None)
    usage = {
        "input_tokens": int(getattr(usage_obj, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage_obj, "output_tokens", 0) or 0),
    }
    log = {
        "request": {"model": model, "system": FORECAST_EXTRACT_PROMPT, "messages": messages},
        "response": {"claims": claims, "drops": drops},
    }
    return claims, drops, usage, log


__all__ = [
    "FORECAST_EXTRACTOR_VERSION",
    "extract_claims",
    "parse_extraction",
    "validate_claims",
]
