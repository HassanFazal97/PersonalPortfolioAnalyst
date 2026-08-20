"""Maps SEC EDGAR filings (Form 4 XML, 13F information tables) to the same
internal dataclass shapes the Congress mapper produces, so one repo upsert
path serves all three notable-trades sources.

Form 4 XML is un-namespaced; 13F info tables carry a namespace that varies
by filer software — parsing is namespace-agnostic (local tag names only).
Every per-row failure degrades to skipping that row, never the filing.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

# Form 4 transaction codes -> our transaction_type vocabulary. P/S are the
# open-market signals users care about; awards/grants/tax withholding are
# "other"; conversions/exercises are "exchange".
_CODE_MAP = {
    "P": "buy",
    "S": "sell",
    "X": "exchange",
    "C": "exchange",
    "M": "exchange",
}


@dataclass
class MappedInsider:
    display_name: str
    slug: str
    company_name: str | None
    company_cik: str | None
    title: str | None
    sec_cik: str | None


@dataclass
class MappedInstitution:
    display_name: str
    slug: str
    fund_name: str | None
    manager_cik: str


@dataclass
class MappedSecTrade:
    source: str
    ticker: str | None
    raw_issuer_name: str | None
    transaction_type: str
    transaction_code: str | None
    transaction_date: date | None
    filed_date: date
    source_url: str | None
    source_document_id: str
    raw_payload: dict[str, Any]
    amount_range_min: Decimal | None = None
    amount_range_max: Decimal | None = None
    cusip: str | None = None
    issuer_cik: str | None = None
    shares: Decimal | None = None
    price_per_share: Decimal | None = None
    value_usd: Decimal | None = None
    quarter_end_date: date | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _slugify(*parts: str | None) -> str:
    raw = "-".join(p for p in parts if p).lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return raw or "unknown"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_text(el: ElementTree.Element | None, *path: str) -> str | None:
    """Namespace-agnostic descent by local tag names; returns stripped text."""
    node = el
    for name in path:
        if node is None:
            return None
        node = next((c for c in node if _local(c.tag) == name), None)
    if node is None or node.text is None:
        return None
    text = node.text.strip()
    return text or None


def _decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None


def _date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _parse_xml(xml_text: str) -> ElementTree.Element | None:
    try:
        return ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        logger.warning("sec_edgar: unparseable XML document")
        return None


def _iter_local(root: ElementTree.Element, name: str):
    for el in root.iter():
        if _local(el.tag) == name:
            yield el


def parse_form4(
    xml_text: str,
    *,
    accession: str,
    filed_date: date,
    source_url: str | None = None,
) -> list[tuple[MappedInsider, MappedSecTrade]]:
    """One Form 4 -> (insider, trade) per non-derivative transaction row.

    Derivative tables (options grants/exercises) are deliberately excluded:
    the feed's product meaning is "insiders buying/selling actual shares."
    """
    root = _parse_xml(xml_text)
    if root is None:
        return []

    issuer = next(_iter_local(root, "issuer"), None)
    issuer_cik_raw = _find_text(issuer, "issuerCik")
    issuer_cik = issuer_cik_raw.zfill(10) if issuer_cik_raw else None
    issuer_name = _find_text(issuer, "issuerName")
    ticker = _find_text(issuer, "issuerTradingSymbol")
    ticker = ticker.upper() if ticker else None

    owner = next(_iter_local(root, "reportingOwner"), None)
    if owner is None:
        return []
    owner_cik_raw = _find_text(owner, "reportingOwnerId", "rptOwnerCik")
    owner_name = _find_text(owner, "reportingOwnerId", "rptOwnerName")
    if not owner_name:
        return []
    rel = next(_iter_local(owner, "reportingOwnerRelationship"), None)
    title = _find_text(rel, "officerTitle") if rel is not None else None
    if not title and rel is not None:
        if (_find_text(rel, "isDirector") or "0") in ("1", "true"):
            title = "Director"
        elif (_find_text(rel, "isTenPercentOwner") or "0") in ("1", "true"):
            title = "10% owner"

    insider = MappedInsider(
        display_name=owner_name,
        slug=_slugify(owner_name, ticker or issuer_cik),
        company_name=issuer_name,
        company_cik=issuer_cik,
        title=title,
        sec_cik=owner_cik_raw.zfill(10) if owner_cik_raw else None,
    )

    out: list[tuple[MappedInsider, MappedSecTrade]] = []
    for idx, tx in enumerate(_iter_local(root, "nonDerivativeTransaction")):
        code = _find_text(tx, "transactionCoding", "transactionCode")
        shares = _decimal(_find_text(tx, "transactionAmounts", "transactionShares", "value"))
        price = _decimal(
            _find_text(tx, "transactionAmounts", "transactionPricePerShare", "value")
        )
        acquired = _find_text(
            tx, "transactionAmounts", "transactionAcquiredDisposedCode", "value"
        )
        tx_date = _date(_find_text(tx, "transactionDate", "value"))
        value = shares * price if shares is not None and price is not None else None
        out.append(
            (
                insider,
                MappedSecTrade(
                    source="sec_form4",
                    ticker=ticker,
                    raw_issuer_name=issuer_name,
                    transaction_type=_CODE_MAP.get(code or "", "other"),
                    transaction_code=code,
                    transaction_date=tx_date,
                    filed_date=filed_date,
                    source_url=source_url,
                    source_document_id=f"{accession}:{idx}",
                    raw_payload={
                        "accession": accession,
                        "code": code,
                        "acquired_disposed": acquired,
                        "shares": str(shares) if shares is not None else None,
                        "price": str(price) if price is not None else None,
                    },
                    cusip=None,
                    issuer_cik=issuer_cik,
                    shares=shares,
                    price_per_share=price,
                    value_usd=value,
                ),
            )
        )
    return out


def parse_13f_holdings(
    xml_text: str,
    *,
    accession: str,
    filed_date: date,
    quarter_end: date | None,
    source_url: str | None = None,
) -> list[MappedSecTrade]:
    """One 13F information table -> one row per holding.

    A 13F is a quarterly holdings *snapshot*, not a trade tape, so rows carry
    ``transaction_type='other'`` with shares/value/cusip populated; quarter-
    over-quarter deltas are a downstream read, not an ingest concern. ``value``
    is whole dollars (the 2023 EDGAR change; older filings in $thousands are
    not re-scaled — filed_date makes the epoch explicit to consumers).
    """
    root = _parse_xml(xml_text)
    if root is None:
        return []
    out: list[MappedSecTrade] = []
    for entry in _iter_local(root, "infoTable"):
        issuer_name = _find_text(entry, "nameOfIssuer")
        cusip = _find_text(entry, "cusip")
        if not cusip:
            continue
        value = _decimal(_find_text(entry, "value"))
        shares = _decimal(_find_text(entry, "shrsOrPrnAmt", "sshPrnamt"))
        put_call = _find_text(entry, "putCall")
        out.append(
            MappedSecTrade(
                source="sec_13f",
                ticker=None,  # CUSIP->ticker is not resolvable from EDGAR alone
                raw_issuer_name=issuer_name,
                transaction_type="other",
                transaction_code=put_call,
                transaction_date=quarter_end,
                filed_date=filed_date,
                source_url=source_url,
                source_document_id=f"{accession}:{cusip}",
                raw_payload={
                    "accession": accession,
                    "put_call": put_call,
                    "value": str(value) if value is not None else None,
                },
                cusip=cusip,
                shares=shares,
                value_usd=value,
                quarter_end_date=quarter_end,
            )
        )
    return out
