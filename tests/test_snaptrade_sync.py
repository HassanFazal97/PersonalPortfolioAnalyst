from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.integrations.snaptrade.sync import sync_wealthsimple_positions
from tests.fakes import FakeRepo


@pytest.mark.asyncio
async def test_sync_wealthsimple_positions_upserts_and_prunes(monkeypatch):
    repo = FakeRepo()
    # Seed a stale row that should be removed.
    await repo.upsert_position(
        ticker="OLD.TO",
        quantity=Decimal("1"),
        avg_cost=Decimal("1"),
        currency="CAD",
        account="TFSA",
    )

    account = {
        "id": "acct-1",
        "raw_type": "TFSA",
        "name": "TFSA",
        "account_category": "INVESTMENT",
    }
    position = {
        "symbol": {"symbol": {"symbol": "NVDA", "currency": {"code": "USD"}}},
        "units": 5,
        "average_purchase_price": 100,
        "currency": {"code": "USD"},
    }

    mock_service = MagicMock()
    mock_service.list_connections.return_value = [{"id": "auth-1"}]
    mock_service.refresh_connection.return_value = False
    mock_service.list_accounts.return_value = [account]
    mock_service.get_account_positions.return_value = [position]

    monkeypatch.setattr(
        "app.integrations.snaptrade.sync.SnapTradeService",
        lambda settings: mock_service,
    )

    summary = await sync_wealthsimple_positions(repo, settings=MagicMock())

    assert summary["positions_upserted"] == 1
    assert summary["positions_removed"] == 1
    assert summary["refresh_skipped"] == 1
    assert summary["tickers"] == ["NVDA"]

    rows = await repo.list_positions()
    assert len(rows) == 1
    assert rows[0].ticker == "NVDA"
    assert rows[0].account == "TFSA"
