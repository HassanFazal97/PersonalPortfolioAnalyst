"""Map SnapTrade accounts and positions into our internal schema."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.tools.tickers import normalize_ticker

VALID_ACCOUNTS = frozenset({"TFSA", "RRSP", "taxable"})


@dataclass(frozen=True)
class MappedPosition:
    ticker: str
    quantity: Decimal
    avg_cost: Decimal
    currency: str
    account: str


def map_account_type(raw_type: str | None, name: str | None = None) -> str:
    """Map a brokerage account to our TFSA / RRSP / taxable enum."""
    blob = f"{raw_type or ''} {name or ''}".upper()
    if "TFSA" in blob:
        return "TFSA"
    if any(tag in blob for tag in ("RRSP", "LIRA", "FHSA", "RRIF", "RESP")):
        return "RRSP"
    return "taxable"


def is_investment_account(account: dict[str, Any]) -> bool:
    category = account.get("account_category")
    return category in (None, "INVESTMENT")


def _dig(obj: Any, *keys: str) -> Any:
    cur = obj
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        qty = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return qty


# Unified-positions instrument kinds our ticker-based schema can't represent.
UNSUPPORTED_KINDS = frozenset({"option", "future", "cfd"})


def extract_yahoo_ticker(position: dict[str, Any]) -> str | None:
    """Extract the Yahoo-format ticker from a SnapTrade position payload."""
    # Unified positions endpoint: {"instrument": {"symbol": "NVDA", ...}}
    ticker = _dig(position, "instrument", "symbol")
    # Legacy positions endpoint: nested symbol objects.
    if not ticker:
        ticker = _dig(position, "symbol", "symbol", "symbol")
    if not ticker:
        ticker = _dig(position, "symbol", "symbol")
    if not ticker:
        ticker = position.get("symbol")
    if isinstance(ticker, dict):
        ticker = ticker.get("symbol")
    if not ticker or not str(ticker).strip():
        return None
    return normalize_ticker(str(ticker))


def extract_currency(position: dict[str, Any]) -> str:
    # Unified positions endpoint: flat currency code string.
    code = position.get("currency")
    if isinstance(code, dict):  # legacy: {"currency": {"code": "CAD"}}
        code = code.get("code")
    if not code:
        code = _dig(position, "instrument", "currency")
    if not code:
        code = _dig(position, "symbol", "symbol", "currency", "code")
    return str(code or "CAD").upper()


def map_position(position: dict[str, Any], *, account: str) -> MappedPosition | None:
    """Convert one SnapTrade position into our positions-table shape."""
    if account not in VALID_ACCOUNTS:
        return None

    kind = _dig(position, "instrument", "kind")
    if kind in UNSUPPORTED_KINDS:
        return None

    ticker = extract_yahoo_ticker(position)
    if not ticker:
        return None

    units = _as_decimal(position.get("units"))
    if units is None or units == 0:
        return None

    # Unified endpoint reports per-unit cost as ``cost_basis``; the legacy
    # endpoint called the same value ``average_purchase_price``.
    avg_cost = _as_decimal(position.get("cost_basis"))
    if avg_cost is None:
        avg_cost = _as_decimal(position.get("average_purchase_price"))
    if avg_cost is None:
        # Fall back to market price so the row is still usable.
        avg_cost = _as_decimal(position.get("price"))
    if avg_cost is None:
        return None

    return MappedPosition(
        ticker=ticker,
        quantity=units,
        avg_cost=avg_cost,
        currency=extract_currency(position),
        account=account,
    )


def map_account_positions(
    account: dict[str, Any], positions: list[dict[str, Any]]
) -> list[MappedPosition]:
    account_type = map_account_type(
        account.get("raw_type"), account.get("name") or account.get("number")
    )
    mapped: list[MappedPosition] = []
    for pos in positions:
        row = map_position(pos, account=account_type)
        if row is not None:
            mapped.append(row)
    return mapped
