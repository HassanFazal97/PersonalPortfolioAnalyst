"""Congress Stock Watcher record mapping: amount parsing, transaction
classification, and the "never drop a filing" degrade-to-None contract."""

from decimal import Decimal

from app.integrations.congress_trades.mapper import (
    classify_transaction_type,
    map_record,
    parse_amount_range,
)


def test_parse_amount_range_two_bounds():
    assert parse_amount_range("$1,001 - $15,000") == (Decimal("1001"), Decimal("15000"))


def test_parse_amount_range_open_upper_bound():
    assert parse_amount_range("$50,000,001 +") == (Decimal("50000001"), None)


def test_parse_amount_range_unparseable():
    assert parse_amount_range(None) == (None, None)
    assert parse_amount_range("N/A") == (None, None)


def test_classify_transaction_type():
    assert classify_transaction_type("Purchase") == "buy"
    assert classify_transaction_type("Sale (Full)") == "sell"
    assert classify_transaction_type("Sale (Partial)") == "sell"
    assert classify_transaction_type("Exchange") == "exchange"
    assert classify_transaction_type("Something Weird") == "other"
    assert classify_transaction_type(None) == "other"


def _senate_row(**overrides):
    row = {
        "senator": "Jane Smith",
        "state": "TX",
        "party": "R",
        "ticker": "NVDA",
        "asset_description": "NVIDIA Corp",
        "type": "Purchase",
        "amount": "$1,001 - $15,000",
        "transaction_date": "2026-08-01",
        "disclosure_date": "2026-08-10",
        "ptr_link": "https://example.com/filing.pdf",
    }
    row.update(overrides)
    return row


def test_map_record_senate_happy_path():
    mapped = map_record(_senate_row(), chamber="senate")
    assert mapped is not None
    investor, trade = mapped
    assert investor.chamber == "senate"
    assert investor.display_name == "Jane Smith"
    assert investor.party == "R"
    assert investor.state == "TX"
    assert trade.source == "senate_stock_watcher"
    assert trade.ticker == "NVDA"
    assert trade.transaction_type == "buy"
    assert trade.amount_range_min == Decimal("1001")
    assert trade.amount_range_max == Decimal("15000")
    assert trade.filed_date.isoformat() == "2026-08-10"
    assert trade.transaction_date.isoformat() == "2026-08-01"


def test_map_record_missing_filed_date_is_dropped():
    assert map_record(_senate_row(disclosure_date=None), chamber="senate") is None


def test_map_record_missing_bioguide_id_falls_back_to_deterministic_slug():
    """No stable member ID in these datasets is common; the fallback must be
    stable across re-syncs so the same member always resolves to one row."""
    mapped1 = map_record(_senate_row(), chamber="senate")
    mapped2 = map_record(_senate_row(), chamber="senate")
    assert mapped1[0].bioguide_id == mapped2[0].bioguide_id
    assert mapped1[0].bioguide_id == "senate:jane-smith"


def test_map_record_unresolvable_ticker_never_drops_the_row():
    mapped = map_record(_senate_row(ticker="--"), chamber="senate")
    assert mapped is not None
    _, trade = mapped
    assert trade.ticker is None
    assert trade.raw_issuer_name == "NVIDIA Corp"


def test_map_record_content_hash_is_stable_across_refetches():
    """Same underlying disclosure fetched twice must produce the same
    source_document_id so the upsert no-ops instead of duplicating."""
    mapped1 = map_record(_senate_row(), chamber="senate")
    mapped2 = map_record(_senate_row(), chamber="senate")
    assert mapped1[1].source_document_id == mapped2[1].source_document_id


def test_map_record_district_derives_state_for_house():
    row = _senate_row()
    del row["senator"], row["state"]
    row["representative"] = "John Doe"
    row["district"] = "TX39"
    mapped = map_record(row, chamber="house")
    assert mapped is not None
    investor, _ = mapped
    assert investor.state == "TX"
    assert investor.chamber == "house"
