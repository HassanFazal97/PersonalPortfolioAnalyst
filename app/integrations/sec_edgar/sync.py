"""Sync jobs: SEC EDGAR Form 4 + 13F -> notable_investors / notable_investor_trades.

Both jobs are incremental via the ``notable_investor_sync_state`` watermark
table (source, external_key=CIK -> last processed filing date), with a small
overlap window; upsert idempotency (source, source_document_id) makes any
re-processing a no-op. Requests are spaced (`_REQUEST_SPACING_SECONDS`) well
under SEC's fair-access ceiling.

Form 4 scope: issuers someone actually cares about — every ticker held or
watched by any user (capped) — resolved to CIKs through the weekly-refreshed
``sec_company_tickers`` map. 13F scope: the configured manager CIK roster.
One entity going dark never blocks the rest.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from app.config import Settings, get_settings
from app.db.repo import Repo
from app.integrations.sec_edgar import client
from app.integrations.sec_edgar.mapper import (
    MappedInstitution,
    _slugify,
    parse_13f_holdings,
    parse_form4,
)

logger = logging.getLogger(__name__)

_REQUEST_SPACING_SECONDS = 0.15
_TICKER_MAP_SOURCE = "sec_company_tickers"
_TICKER_MAP_MAX_AGE_DAYS = 7
FORM4_LOOKBACK_DAYS = 14  # first-sync window per issuer; watermark thereafter
THIRTEENF_LOOKBACK_DAYS = 120


async def ensure_company_tickers(repo: Repo, settings: Settings) -> int:
    """Refresh the CIK<->ticker map when empty or older than a week."""
    stamp = await repo.get_sync_watermark(_TICKER_MAP_SOURCE, "global")
    fresh = (
        stamp is not None
        and date.fromisoformat(stamp) > date.today() - timedelta(days=_TICKER_MAP_MAX_AGE_DAYS)
    )
    if fresh and await repo.sec_company_tickers_count() > 0:
        return 0
    rows = await client.fetch_company_tickers(settings)
    if not rows:
        return 0  # fail open: keep the stale map
    count = await repo.upsert_sec_company_tickers(rows)
    await repo.set_sync_watermark(_TICKER_MAP_SOURCE, "global", date.today().isoformat())
    return count


def _recent_filings(submissions: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the submissions feed's parallel arrays into filing dicts."""
    recent = (submissions.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    out = []
    for i, form in enumerate(forms):
        def _col(key: str) -> Any:
            values = recent.get(key) or []
            return values[i] if i < len(values) else None

        # Ownership forms list primaryDocument behind an XSL-viewer prefix
        # ("xslF345X06/wk-form4_....xml") — that path serves the rendered
        # HTML; the raw XML is the bare filename after the slash.
        primary = _col("primaryDocument")
        if primary:
            primary = primary.rsplit("/", 1)[-1]
        out.append(
            {
                "form": form,
                "accession": _col("accessionNumber"),
                "filing_date": _col("filingDate"),
                "primary_document": primary,
                "report_date": _col("reportDate"),
            }
        )
    return out


async def _form4_scope(repo: Repo, settings: Settings) -> list[str]:
    held = await repo.list_distinct_position_tickers()
    watched = await repo.list_distinct_watchlist_tickers()
    # US listings only: EDGAR has no TSX filers (".TO" etc. never resolve).
    tickers = sorted({t for t in held + watched if t and "." not in t})
    return tickers[: settings.form4_max_issuers]


async def sync_form4(repo: Repo, *, settings: Settings | None = None) -> dict[str, Any]:
    """Poll the submissions feed per in-scope issuer; ingest new Form 4s."""
    settings = settings or get_settings()
    summary: dict[str, Any] = {"issuers": 0, "filings": 0, "trades_new": 0, "errors": 0}
    summary["ticker_map_refreshed"] = await ensure_company_tickers(repo, settings)

    tickers = await _form4_scope(repo, settings)
    cik_by_ticker = await repo.get_ciks_for_tickers(tickers)
    summary["issuers"] = len(cik_by_ticker)

    for ticker, cik in cik_by_ticker.items():
        try:
            await asyncio.sleep(_REQUEST_SPACING_SECONDS)
            submissions = await client.fetch_submissions(cik, settings)
            if submissions is None:
                summary["errors"] += 1
                continue
            watermark = await repo.get_sync_watermark("sec_form4", cik)
            floor = (
                date.fromisoformat(watermark)
                if watermark
                else date.today() - timedelta(days=FORM4_LOOKBACK_DAYS)
            )
            latest = floor
            for filing in _recent_filings(submissions):
                if filing["form"] not in ("4", "4/A"):
                    continue
                filed = filing["filing_date"]
                if not filed or date.fromisoformat(filed) < floor:
                    continue
                accession, doc = filing["accession"], filing["primary_document"]
                if not accession or not doc:
                    continue
                await asyncio.sleep(_REQUEST_SPACING_SECONDS)
                xml_text = await client.fetch_document(cik, accession, doc, settings)
                if xml_text is None:
                    summary["errors"] += 1
                    continue
                summary["filings"] += 1
                filed_date = date.fromisoformat(filed)
                for insider, trade in parse_form4(
                    xml_text,
                    accession=accession,
                    filed_date=filed_date,
                    source_url=client._archive_url(cik, accession, doc),
                ):
                    investor_id = await repo.upsert_insider_investor(insider)
                    if await repo.upsert_notable_investor_trade(
                        investor_id=investor_id, trade=trade
                    ):
                        summary["trades_new"] += 1
                latest = max(latest, filed_date)
            # Re-scan the last day on the next run (same-day late filings);
            # idempotent upserts make the overlap free.
            await repo.set_sync_watermark("sec_form4", cik, latest.isoformat())
        except Exception:  # noqa: BLE001 - one issuer never blocks the rest
            summary["errors"] += 1
            logger.warning("sec_form4 sync failed for %s (%s)", ticker, cik, exc_info=True)
    return summary


def _find_infotable(filenames: list[str], primary_document: str | None) -> str | None:
    """The information-table XML's name varies by filer software; prefer an
    explicit 'infotable' name, else any XML that isn't the cover document."""
    xmls = [f for f in filenames if f.lower().endswith(".xml")]
    for f in xmls:
        if "infotable" in f.lower():
            return f
    others = [f for f in xmls if f != primary_document]
    return others[0] if others else None


async def sync_13f(repo: Repo, *, settings: Settings | None = None) -> dict[str, Any]:
    """Poll the configured 13F manager roster; ingest new holdings tables."""
    settings = settings or get_settings()
    summary: dict[str, Any] = {"managers": 0, "filings": 0, "holdings_new": 0, "errors": 0}
    ciks = [c.strip().zfill(10) for c in settings.thirteenf_manager_ciks.split(",") if c.strip()]
    summary["managers"] = len(ciks)

    for cik in ciks:
        try:
            await asyncio.sleep(_REQUEST_SPACING_SECONDS)
            submissions = await client.fetch_submissions(cik, settings)
            if submissions is None:
                summary["errors"] += 1
                continue
            name = submissions.get("name") or f"CIK {cik}"
            watermark = await repo.get_sync_watermark("sec_13f", cik)
            floor = (
                date.fromisoformat(watermark)
                if watermark
                else date.today() - timedelta(days=THIRTEENF_LOOKBACK_DAYS)
            )
            latest = floor
            for filing in _recent_filings(submissions):
                if filing["form"] not in ("13F-HR", "13F-HR/A"):
                    continue
                filed = filing["filing_date"]
                if not filed or date.fromisoformat(filed) <= floor:
                    continue
                accession = filing["accession"]
                if not accession:
                    continue
                await asyncio.sleep(_REQUEST_SPACING_SECONDS)
                filenames = await client.fetch_filing_index(cik, accession, settings)
                infotable = _find_infotable(filenames, filing["primary_document"])
                if infotable is None:
                    summary["errors"] += 1
                    continue
                await asyncio.sleep(_REQUEST_SPACING_SECONDS)
                xml_text = await client.fetch_document(cik, accession, infotable, settings)
                if xml_text is None:
                    summary["errors"] += 1
                    continue
                summary["filings"] += 1
                filed_date = date.fromisoformat(filed)
                holdings = parse_13f_holdings(
                    xml_text,
                    accession=accession,
                    filed_date=filed_date,
                    quarter_end=(
                        date.fromisoformat(filing["report_date"])
                        if filing["report_date"]
                        else None
                    ),
                    source_url=client._archive_url(cik, accession, infotable),
                )
                # Whale funds file thousands of positions; keep the top slice
                # by reported value (the product story is "what the whales'
                # big bets are", not an exhaustive mirror).
                holdings.sort(key=lambda h: h.value_usd or 0, reverse=True)
                holdings = holdings[: settings.thirteenf_max_holdings]
                investor_id = await repo.upsert_institution_investor(
                    MappedInstitution(
                        display_name=name,
                        slug=_slugify(name),
                        fund_name=name,
                        manager_cik=cik,
                    )
                )
                for trade in holdings:
                    if await repo.upsert_notable_investor_trade(
                        investor_id=investor_id, trade=trade
                    ):
                        summary["holdings_new"] += 1
                latest = max(latest, filed_date)
            await repo.set_sync_watermark("sec_13f", cik, latest.isoformat())
        except Exception:  # noqa: BLE001 - one manager never blocks the rest
            summary["errors"] += 1
            logger.warning("sec_13f sync failed for CIK %s", cik, exc_info=True)
    return summary
