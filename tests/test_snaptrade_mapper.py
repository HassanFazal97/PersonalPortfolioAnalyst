"""Tests for SnapTrade → positions mapping."""

from decimal import Decimal

from app.integrations.snaptrade.mapper import (
    extract_yahoo_ticker,
    is_investment_account,
    map_account_positions,
    map_account_type,
    map_position,
)


def _position(
    *,
    ticker: str = "SHOP.TO",
    units: float = 10,
    avg_cost: float = 45.5,
    currency: str = "CAD",
    kind: str = "stock",
) -> dict:
    """Unified positions endpoint shape (GET /accounts/{id}/positions/all)."""
    return {
        "instrument": {
            "kind": kind,
            "symbol": ticker,
            "raw_symbol": ticker,
            "currency": currency,
            "exchange": "XTSE",
        },
        "units": str(units),
        "price": "50.00",
        "cost_basis": str(avg_cost),
        "currency": currency,
    }


def _legacy_position(
    *,
    ticker: str = "SHOP.TO",
    units: float = 10,
    avg_cost: float = 45.5,
    currency: str = "CAD",
) -> dict:
    """Deprecated positions endpoint shape (GET /accounts/{id}/positions)."""
    return {
        "symbol": {
            "symbol": {
                "symbol": ticker,
                "currency": {"code": currency},
            }
        },
        "units": units,
        "average_purchase_price": avg_cost,
        "currency": {"code": currency},
    }


def test_map_account_type_tfsa():
    assert map_account_type("TFSA", "My TFSA") == "TFSA"


def test_map_account_type_rrsp():
    assert map_account_type("RRSP", "Retirement") == "RRSP"
    assert map_account_type("LIRA", None) == "RRSP"


def test_map_account_type_taxable_default():
    assert map_account_type("NON_REGISTERED", "Personal") == "taxable"
    assert map_account_type(None, "Margin") == "taxable"


def test_is_investment_account():
    assert is_investment_account({"account_category": "INVESTMENT"})
    assert is_investment_account({"account_category": None})
    assert not is_investment_account({"account_category": "DEPOSIT"})


def test_extract_yahoo_ticker_nested():
    assert extract_yahoo_ticker(_position(ticker="NVDA")) == "NVDA"
    assert extract_yahoo_ticker(_position(ticker="RY.TO")) == "RY.TO"


def test_map_position_skips_zero_units():
    assert map_position(_position(units=0), account="TFSA") is None


def test_map_position_maps_fields():
    row = map_position(_position(), account="TFSA")
    assert row is not None
    assert row.ticker == "SHOP.TO"
    assert row.quantity == Decimal("10")
    assert row.avg_cost == Decimal("45.5")
    assert row.currency == "CAD"
    assert row.account == "TFSA"


def test_map_position_legacy_shape():
    row = map_position(_legacy_position(), account="TFSA")
    assert row is not None
    assert row.ticker == "SHOP.TO"
    assert row.quantity == Decimal("10")
    assert row.avg_cost == Decimal("45.5")
    assert row.currency == "CAD"


def test_map_position_skips_derivatives():
    assert map_position(_position(kind="option"), account="TFSA") is None
    assert map_position(_position(kind="future"), account="TFSA") is None
    assert map_position(_position(kind="cfd"), account="TFSA") is None
    assert map_position(_position(kind="crypto"), account="TFSA") is not None


def test_map_position_falls_back_to_price_without_cost_basis():
    pos = _position()
    del pos["cost_basis"]
    row = map_position(pos, account="TFSA")
    assert row is not None
    assert row.avg_cost == Decimal("50.00")


def test_map_account_positions_batch():
    account = {"id": "acct-1", "raw_type": "TFSA", "name": "TFSA"}
    rows = map_account_positions(account, [_position(), _position(ticker="NVDA", units=2)])
    assert len(rows) == 2
    assert {r.ticker for r in rows} == {"SHOP.TO", "NVDA"}
