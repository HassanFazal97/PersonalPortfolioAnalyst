"""sync_form4 / sync_13f: watermarks, idempotency, per-entity fail-open."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.config import get_settings
from app.integrations.sec_edgar import sync
from tests.test_sec_edgar_mapper import FORM4_XML, THIRTEENF_XML

TODAY = dt.date.today()
RECENT = (TODAY - dt.timedelta(days=2)).isoformat()


class StubRepo:
    def __init__(self):
        self.company_tickers: dict[str, str] = {"AAPL": "0000320193"}
        self.watermarks: dict[tuple[str, str], str] = {
            ("sec_company_tickers", "global"): TODAY.isoformat()
        }
        self.investors: dict[str, uuid.UUID] = {}
        self.trades: set[tuple[str, str]] = set()
        self.position_tickers = ["AAPL", "SHOP.TO"]
        self.watchlist_tickers = ["NVDA"]

    async def get_sync_watermark(self, source, key):
        return self.watermarks.get((source, key))

    async def set_sync_watermark(self, source, key, value):
        self.watermarks[(source, key)] = value

    async def sec_company_tickers_count(self):
        return len(self.company_tickers)

    async def upsert_sec_company_tickers(self, rows):
        for r in rows:
            self.company_tickers[r["ticker"]] = r["cik"]
        return len(rows)

    async def get_ciks_for_tickers(self, tickers):
        return {t: c for t, c in self.company_tickers.items() if t in tickers}

    async def list_distinct_position_tickers(self):
        return self.position_tickers

    async def list_distinct_watchlist_tickers(self):
        return self.watchlist_tickers

    async def upsert_insider_investor(self, investor):
        return self.investors.setdefault(f"insider:{investor.sec_cik}", uuid.uuid4())

    async def upsert_institution_investor(self, investor):
        return self.investors.setdefault(f"inst:{investor.manager_cik}", uuid.uuid4())

    async def upsert_notable_investor_trade(self, *, investor_id, trade):
        key = (trade.source, trade.source_document_id)
        if key in self.trades:
            return False
        self.trades.add(key)
        return True


SUBMISSIONS_FORM4 = {
    "name": "Apple Inc.",
    "filings": {
        "recent": {
            "form": ["4", "10-K", "4"],
            "accessionNumber": ["0001-26-000123", "0001-26-000122", "0001-26-000100"],
            "filingDate": [RECENT, RECENT, "2020-01-01"],  # old one below floor
            "primaryDocument": ["form4.xml", "aapl-10k.htm", "form4.xml"],
            "reportDate": [RECENT, RECENT, "2020-01-01"],
        }
    },
}

SUBMISSIONS_13F = {
    "name": "Berkshire Hathaway Inc",
    "filings": {
        "recent": {
            "form": ["13F-HR", "8-K"],
            "accessionNumber": ["0002-26-000009", "0002-26-000008"],
            "filingDate": [RECENT, RECENT],
            "primaryDocument": ["primary_doc.xml", "bk-8k.htm"],
            "reportDate": ["2026-06-30", RECENT],
        }
    },
}


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def instant(_):
        return None

    monkeypatch.setattr(sync.asyncio, "sleep", instant)


@pytest.fixture
def repo():
    return StubRepo()


def _patch_client(monkeypatch, *, submissions, document, index=None):
    async def fake_submissions(cik, settings):
        return submissions

    async def fake_document(cik, accession, filename, settings):
        return document

    async def fake_index(cik, accession, settings):
        return index or []

    async def fake_company_tickers(settings):
        return []

    monkeypatch.setattr(sync.client, "fetch_submissions", fake_submissions)
    monkeypatch.setattr(sync.client, "fetch_document", fake_document)
    monkeypatch.setattr(sync.client, "fetch_filing_index", fake_index)
    monkeypatch.setattr(sync.client, "fetch_company_tickers", fake_company_tickers)


async def test_sync_form4_ingests_and_is_idempotent(monkeypatch, repo):
    _patch_client(monkeypatch, submissions=SUBMISSIONS_FORM4, document=FORM4_XML)
    s1 = await sync.sync_form4(repo, settings=get_settings())
    # Only AAPL resolves (SHOP.TO excluded as non-US, NVDA has no CIK in map);
    # one recent Form 4 with two transactions; the 2020 filing is below floor.
    assert s1["issuers"] == 1 and s1["filings"] == 1 and s1["trades_new"] == 2
    assert repo.watermarks[("sec_form4", "0000320193")] == RECENT
    s2 = await sync.sync_form4(repo, settings=get_settings())
    assert s2["trades_new"] == 0  # upsert dedup makes the re-scan free


async def test_sync_form4_fetch_failure_counts_error(monkeypatch, repo):
    async def none_submissions(cik, settings):
        return None

    _patch_client(monkeypatch, submissions=SUBMISSIONS_FORM4, document=FORM4_XML)
    monkeypatch.setattr(sync.client, "fetch_submissions", none_submissions)
    s = await sync.sync_form4(repo, settings=get_settings())
    assert s["errors"] == 1 and s["trades_new"] == 0


async def test_sync_13f_ingests_top_holdings(monkeypatch, repo):
    _patch_client(
        monkeypatch,
        submissions=SUBMISSIONS_13F,
        document=THIRTEENF_XML,
        index=["primary_doc.xml", "infotable.xml"],
    )
    monkeypatch.setattr(
        get_settings(), "thirteenf_manager_ciks", "0001067983", raising=False
    )
    s1 = await sync.sync_13f(repo, settings=get_settings())
    assert s1["managers"] == 1 and s1["filings"] == 1 and s1["holdings_new"] == 2
    assert "inst:0001067983" in repo.investors
    assert repo.watermarks[("sec_13f", "0001067983")] == RECENT
    s2 = await sync.sync_13f(repo, settings=get_settings())
    assert s2["holdings_new"] == 0 and s2["filings"] == 0  # watermark skips it
