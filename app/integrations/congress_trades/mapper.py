"""Maps raw Senate/House Stock Watcher records to internal dataclasses.

Both datasets are unofficial and their exact field names have drifted over
the years (community-maintained scrapers, no versioned schema). Every read
here goes through ``_first()`` so a renamed/missing field degrades to None
rather than raising and losing an otherwise-good row.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.tools.tickers import normalize_ticker

# Raw "type"/"asset_type" strings seen across both datasets, lowercased.
_BUY_TYPES = {"purchase", "purchase (partial)"}
_SELL_TYPES = {
    "sale",
    "sale (full)",
    "sale (partial)",
    "sale (full)".lower(),
}
_EXCHANGE_TYPES = {"exchange"}

# "$1,001 - $15,000" / "$1,001–$15,000" / "$50,000,001 +" style ranges.
_AMOUNT_RE = re.compile(r"\$?([\d,]+)")


def _first(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def _slugify(*parts: str) -> str:
    raw = "-".join(p for p in parts if p).lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return raw or "unknown"


def classify_transaction_type(raw: str | None) -> str:
    if not raw:
        return "other"
    key = raw.strip().lower()
    if key in _BUY_TYPES or key.startswith("purchase"):
        return "buy"
    if key in _SELL_TYPES or key.startswith("sale"):
        return "sell"
    if key in _EXCHANGE_TYPES:
        return "exchange"
    return "other"


def parse_amount_range(raw: str | None) -> tuple[Decimal | None, Decimal | None]:
    """"$1,001 - $15,000" -> (1001, 15000). A single-bound "$50,000,001 +"
    style range maps to (50000001, None). Unparseable input -> (None, None)."""
    if not raw:
        return None, None
    numbers = _AMOUNT_RE.findall(raw)
    if not numbers:
        return None, None
    try:
        parsed = [Decimal(n.replace(",", "")) for n in numbers]
    except InvalidOperation:
        return None, None
    if len(parsed) == 1:
        return parsed[0], None
    return parsed[0], parsed[1]


def _parse_date(raw: Any) -> date | None:
    if not raw:
        return None
    if isinstance(raw, date):
        return raw
    text = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class MappedInvestor:
    """A congress member identity, keyed by ``bioguide_id`` (real one if the
    source provides it, else a deterministic slug of chamber+name — either
    way stable across re-syncs, which is what the DB unique index relies on)."""

    bioguide_id: str
    display_name: str
    slug: str
    chamber: str  # senate | house
    party: str | None
    state: str | None


@dataclass(frozen=True)
class MappedTrade:
    source: str  # senate_stock_watcher | house_stock_watcher
    source_document_id: str
    ticker: str | None
    raw_issuer_name: str | None
    transaction_type: str
    transaction_code: str | None
    amount_range_min: Decimal | None
    amount_range_max: Decimal | None
    transaction_date: date | None
    filed_date: date
    source_url: str | None
    raw_payload: dict[str, Any]


def map_record(raw: dict[str, Any], *, chamber: str) -> tuple[MappedInvestor, MappedTrade] | None:
    """Map one raw JSON record to (investor, trade). Returns None only when
    the record is missing a filed_date — every other field degrades to None/
    'other' rather than dropping the row, per the "never drop a filing"
    policy in the ingestion design."""
    source = "senate_stock_watcher" if chamber == "senate" else "house_stock_watcher"

    name = _first(raw, "senator", "representative", "member", "name")
    if not name:
        name = "Unknown member"
    bioguide_id = _first(raw, "bioguide_id", "bioguideId")
    if not bioguide_id:
        # Deterministic fallback so the same member always resolves to the
        # same investor row even though these datasets rarely include a
        # stable member ID.
        bioguide_id = f"{chamber}:{_slugify(name)}"
    state = _first(raw, "state")
    district = _first(raw, "district")
    if not state and district and len(str(district)) >= 2:
        state = str(district)[:2].upper()
    party = _first(raw, "party")

    investor = MappedInvestor(
        bioguide_id=str(bioguide_id),
        display_name=str(name),
        slug=_slugify(chamber, name),
        chamber=chamber,
        party=str(party) if party else None,
        state=str(state) if state else None,
    )

    filed_date = _parse_date(_first(raw, "disclosure_date", "disclosureDate"))
    if filed_date is None:
        return None
    transaction_date = _parse_date(_first(raw, "transaction_date", "transactionDate"))

    raw_ticker = _first(raw, "ticker", "symbol")
    ticker: str | None = None
    if raw_ticker and str(raw_ticker).strip() not in ("--", "N/A"):
        try:
            ticker = normalize_ticker(str(raw_ticker))
        except ValueError:
            ticker = None

    raw_type = _first(raw, "type", "transaction_type")
    amount_raw = _first(raw, "amount")
    amount_min, amount_max = parse_amount_range(str(amount_raw) if amount_raw else None)

    # Content-based dedup key: these datasets have no stable filing/row ID, so
    # a re-fetch of the same underlying disclosure must reproduce the same
    # hash for the upsert to no-op instead of duplicating.
    hash_input = "|".join(
        str(x)
        for x in (
            investor.bioguide_id,
            ticker or _first(raw, "asset_description") or "",
            transaction_date or "",
            raw_type or "",
            amount_raw or "",
            filed_date,
        )
    )
    source_document_id = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:32]

    trade = MappedTrade(
        source=source,
        source_document_id=source_document_id,
        ticker=ticker,
        raw_issuer_name=_first(raw, "asset_description", "asset_type"),
        transaction_type=classify_transaction_type(str(raw_type) if raw_type else None),
        transaction_code=str(raw_type) if raw_type else None,
        amount_range_min=amount_min,
        amount_range_max=amount_max,
        transaction_date=transaction_date,
        filed_date=filed_date,
        source_url=_first(raw, "ptr_link", "ptrLink"),
        raw_payload=raw,
    )
    return investor, trade
