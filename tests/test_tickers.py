import pytest

from app.tools.tickers import normalize_ticker, normalize_tickers


def test_uppercases_and_trims():
    assert normalize_ticker("  nvda ") == "NVDA"


def test_preserves_exchange_suffix():
    assert normalize_ticker("shop.to") == "SHOP.TO"


def test_class_share_uses_hyphen():
    assert normalize_ticker("brk.b") == "BRK-B"
    assert normalize_ticker("BRK.A") == "BRK-A"


def test_empty_raises():
    with pytest.raises(ValueError):
        normalize_ticker("   ")


def test_normalize_tickers_dedupes_preserving_order():
    assert normalize_tickers(["NVDA", "nvda", "SHOP.TO", "shop.to"]) == [
        "NVDA",
        "SHOP.TO",
    ]
