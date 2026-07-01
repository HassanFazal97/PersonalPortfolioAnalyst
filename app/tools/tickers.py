"""Ticker normalization to Yahoo Finance format, applied at every input boundary.

Yahoo format examples: ``NVDA``, ``SHOP.TO``, ``RY.TO``, ``BRK-B``.
We uppercase, trim whitespace, and map a few common alternate spellings
(e.g. ``BRK.B`` -> ``BRK-B``). Exchange suffixes like ``.TO`` are preserved.
"""

from __future__ import annotations

# Class-share tickers use a hyphen in Yahoo format, not a dot.
_CLASS_SHARE_FIXUPS = {
    "BRK.A": "BRK-A",
    "BRK.B": "BRK-B",
    "BF.A": "BF-A",
    "BF.B": "BF-B",
}


def normalize_ticker(raw: str) -> str:
    if not raw or not raw.strip():
        raise ValueError("ticker must be a non-empty string")
    t = raw.strip().upper()
    if t in _CLASS_SHARE_FIXUPS:
        return _CLASS_SHARE_FIXUPS[t]
    return t


def normalize_tickers(raws: list[str]) -> list[str]:
    """Normalize and de-duplicate while preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in raws:
        t = normalize_ticker(raw)
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out
