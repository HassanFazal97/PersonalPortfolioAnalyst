"""Form 4 / 13F XML parsing against hand-built fixture documents."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.integrations.sec_edgar.mapper import parse_13f_holdings, parse_form4

FORM4_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>320193</issuerCik>
    <issuerName>Apple Inc.</issuerName>
    <issuerTradingSymbol>aapl</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>1214156</rptOwnerCik>
      <rptOwnerName>COOK TIMOTHY D</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>0</isDirector>
      <isOfficer>1</isOfficer>
      <officerTitle>Chief Executive Officer</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-08-14</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>10000</value></transactionShares>
        <transactionPricePerShare><value>228.50</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-08-15</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>500</value></transactionShares>
        <transactionPricePerShare><value>230.00</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
  <derivativeTable>
    <derivativeTransaction>
      <transactionCoding><transactionCode>M</transactionCode></transactionCoding>
    </derivativeTransaction>
  </derivativeTable>
</ownershipDocument>"""

THIRTEENF_XML = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <cusip>037833100</cusip>
    <value>91000000000</value>
    <shrsOrPrnAmt><sshPrnamt>400000000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>OCCIDENTAL PETE CORP</nameOfIssuer>
    <cusip>674599105</cusip>
    <value>13000000000</value>
    <shrsOrPrnAmt><sshPrnamt>250000000</sshPrnamt></shrsOrPrnAmt>
    <putCall>Put</putCall>
  </infoTable>
  <infoTable>
    <nameOfIssuer>NO CUSIP CORP</nameOfIssuer>
    <value>1</value>
  </infoTable>
</informationTable>"""

FILED = dt.date(2026, 8, 18)


def test_parse_form4_exact():
    rows = parse_form4(FORM4_XML, accession="0001-26-000123", filed_date=FILED)
    assert len(rows) == 2  # derivative table excluded
    insider, sale = rows[0]
    assert insider.display_name == "COOK TIMOTHY D"
    assert insider.sec_cik == "0001214156" and insider.company_cik == "0000320193"
    assert insider.title == "Chief Executive Officer"
    assert sale.source == "sec_form4" and sale.ticker == "AAPL"
    assert sale.transaction_type == "sell" and sale.transaction_code == "S"
    assert sale.shares == Decimal("10000")
    assert sale.value_usd == Decimal("10000") * Decimal("228.50")
    assert sale.transaction_date == dt.date(2026, 8, 14)
    assert sale.source_document_id == "0001-26-000123:0"
    _, buy = rows[1]
    assert buy.transaction_type == "buy"
    assert buy.source_document_id == "0001-26-000123:1"


def test_parse_form4_director_title_fallback():
    xml = FORM4_XML.replace(
        "<officerTitle>Chief Executive Officer</officerTitle>", ""
    ).replace("<isDirector>0</isDirector>", "<isDirector>1</isDirector>")
    insider, _ = parse_form4(xml, accession="a", filed_date=FILED)[0]
    assert insider.title == "Director"


def test_parse_form4_garbage_returns_empty():
    assert parse_form4("not xml", accession="a", filed_date=FILED) == []
    assert parse_form4("<ownershipDocument/>", accession="a", filed_date=FILED) == []


def test_parse_13f_holdings_namespace_and_fields():
    q_end = dt.date(2026, 6, 30)
    rows = parse_13f_holdings(
        THIRTEENF_XML, accession="0002-26-000009", filed_date=FILED, quarter_end=q_end
    )
    assert len(rows) == 2  # the cusip-less row is dropped
    aapl = rows[0]
    assert aapl.source == "sec_13f" and aapl.cusip == "037833100"
    assert aapl.ticker is None and aapl.raw_issuer_name == "APPLE INC"
    assert aapl.value_usd == Decimal("91000000000")
    assert aapl.shares == Decimal("400000000")
    assert aapl.quarter_end_date == q_end and aapl.transaction_date == q_end
    assert aapl.source_document_id == "0002-26-000009:037833100"
    assert rows[1].transaction_code == "Put"
