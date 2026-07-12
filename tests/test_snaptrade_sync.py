import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import DEFAULT_USER_ID
from app.integrations.snaptrade.sync import sync_brokerage_positions
from tests.fakes import FakeRepo


@pytest.mark.asyncio
async def test_sync_brokerage_positions_upserts_and_prunes(monkeypatch):
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
        "instrument": {"kind": "stock", "symbol": "NVDA", "currency": "USD"},
        "units": "5",
        "price": "110",
        "cost_basis": "100",
        "currency": "USD",
    }

    mock_service = MagicMock()
    mock_service.list_connections.return_value = [{"id": "auth-1"}]
    mock_service.refresh_connection.return_value = False
    mock_service.list_accounts.return_value = [account]
    mock_service.get_account_positions.return_value = [position]

    monkeypatch.setattr(
        "app.integrations.snaptrade.sync.service_for_user",
        AsyncMock(return_value=mock_service),
    )

    summary = await sync_brokerage_positions(
        repo, user_id=uuid.UUID(DEFAULT_USER_ID), settings=MagicMock()
    )

    assert summary["positions_upserted"] == 1
    assert summary["positions_removed"] == 1
    assert summary["refresh_skipped"] == 1
    assert summary["tickers"] == ["NVDA"]

    rows = await repo.list_positions()
    assert len(rows) == 1
    assert rows[0].ticker == "NVDA"
    assert rows[0].account == "TFSA"


@pytest.mark.asyncio
async def test_sync_merges_accounts_that_share_a_bucket(monkeypatch):
    # RRSP and FHSA both map to the "RRSP" bucket; the same ticker held in
    # both must be summed, not overwritten by whichever account syncs last.
    repo = FakeRepo()
    rrsp = {"id": "acct-1", "raw_type": "RRSP", "name": "RRSP",
            "account_category": "INVESTMENT"}
    fhsa = {"id": "acct-2", "raw_type": "FHSA", "name": "FHSA",
            "account_category": "INVESTMENT"}

    def _pos(units, cost):
        return {
            "instrument": {"kind": "stock", "symbol": "VFV", "currency": "CAD"},
            "units": units, "price": "150", "cost_basis": cost, "currency": "CAD",
        }

    mock_service = MagicMock()
    mock_service.list_connections.return_value = []
    mock_service.list_accounts.return_value = [rrsp, fhsa]
    mock_service.get_account_positions.side_effect = lambda aid: (
        [_pos("10", "100")] if aid == "acct-1" else [_pos("30", "120")]
    )

    monkeypatch.setattr(
        "app.integrations.snaptrade.sync.service_for_user",
        AsyncMock(return_value=mock_service),
    )

    summary = await sync_brokerage_positions(
        repo, user_id=uuid.UUID(DEFAULT_USER_ID), settings=MagicMock()
    )

    assert summary["positions_upserted"] == 1
    rows = await repo.list_positions()
    assert len(rows) == 1
    assert rows[0].account == "RRSP"
    assert rows[0].quantity == Decimal("40")
    # Weighted average cost: (10*100 + 30*120) / 40 = 115
    assert rows[0].avg_cost == Decimal("115")
