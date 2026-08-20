"""Thin HTTP client for SEC EDGAR (Form 4 insider filings, 13F holdings).

Unlike the Congress mirrors, this IS the official structured source. Two
rules govern every request (SEC fair-access policy): a descriptive
User-Agent with a contact address (``SEC_EDGAR_USER_AGENT``), and a polite
request rate (the sync layer spaces calls; SEC's stated ceiling is 10/s).

Every fetch fails open (None/[]) — callers treat a missing document as
"skip this filing", never as a reason to abort a sync or wipe rows.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{filename}"


def _headers(settings: Settings) -> dict[str, str]:
    return {"User-Agent": settings.sec_edgar_user_agent}


async def _get(url: str, *, settings: Settings) -> httpx.Response | None:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_headers(settings)) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp
    except Exception:  # noqa: BLE001 - callers fail open per document
        logger.warning("sec_edgar fetch failed: %s", url, exc_info=True)
        return None


async def fetch_company_tickers(settings: Settings) -> list[dict[str, Any]]:
    """SEC's CIK<->ticker map as {"cik","ticker","title"} rows (cik as the
    zero-padded 10-digit string used everywhere else in EDGAR)."""
    resp = await _get(COMPANY_TICKERS_URL, settings=settings)
    if resp is None:
        return []
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return []
    rows = []
    for entry in (data or {}).values():
        if not isinstance(entry, dict):
            continue
        cik, ticker = entry.get("cik_str"), entry.get("ticker")
        if cik is None or not ticker:
            continue
        rows.append(
            {
                "cik": str(int(cik)).zfill(10),
                "ticker": str(ticker).upper(),
                "title": entry.get("title"),
            }
        )
    return rows


async def fetch_submissions(cik: str, settings: Settings) -> dict[str, Any] | None:
    """The per-entity submissions feed (recent filings, entity name)."""
    resp = await _get(SUBMISSIONS_URL.format(cik=cik.zfill(10)), settings=settings)
    if resp is None:
        return None
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def _archive_url(cik: str, accession: str, filename: str) -> str:
    return ARCHIVES_URL.format(
        cik_int=int(cik),
        accession_nodash=accession.replace("-", ""),
        filename=filename,
    )


async def fetch_document(
    cik: str, accession: str, filename: str, settings: Settings
) -> str | None:
    """One filing document's raw text (Form 4 XML, 13F info table XML)."""
    resp = await _get(_archive_url(cik, accession, filename), settings=settings)
    return resp.text if resp is not None else None


async def fetch_filing_index(
    cik: str, accession: str, settings: Settings
) -> list[str]:
    """Filenames inside one filing (index.json) — used to locate the 13F
    information-table XML, whose name varies by filer software."""
    resp = await _get(_archive_url(cik, accession, "index.json"), settings=settings)
    if resp is None:
        return []
    try:
        items = resp.json().get("directory", {}).get("item", [])
    except Exception:  # noqa: BLE001
        return []
    return [i.get("name", "") for i in items if isinstance(i, dict)]
