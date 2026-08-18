-- Notable Investor Trades: tracks disclosed trading activity from Congress
-- members, corporate insiders (SEC Form 4), and institutional/hedge funds
-- (SEC 13F), plus a per-user "follow a person" list and digest idempotency.
--
-- notable_investors / notable_investor_trades / notable_investor_sync_state /
-- sec_company_tickers are GLOBAL tables (market/public-filing data shared by
-- every user, populated by scheduled sync jobs under the owner service
-- context) — same posture as stock_picks_runs/daily_prices: any app-set GUC
-- may read/write; Pro gating is enforced at the API route, not in RLS.
--
-- notable_investor_follows and notable_trade_digest_mentions are tenant
-- tables (per-user), same posture as watchlist_items/funnel_events.

CREATE TABLE IF NOT EXISTS notable_investors (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  investor_type     text NOT NULL,          -- 'congress' | 'insider' | 'institution'
  display_name      text NOT NULL,
  slug              text NOT NULL,          -- url-safe, unique, for follow deep-links
  -- congress-specific
  chamber           text,                   -- 'senate' | 'house'
  party             text,
  state             text,
  bioguide_id       text,                   -- external id from Stock Watcher datasets
  -- insider-specific (a person is scoped per-issuer: Form 4 reporting
  -- relationships are issuer-scoped, so the same human at two companies is
  -- two rows rather than one fuzzy cross-company identity)
  company_name      text,
  company_cik        text,                  -- issuer's SEC CIK, zero-padded 10-digit string
  title             text,                   -- officer/director title from Form 4
  -- institution-specific
  fund_name         text,
  manager_cik       text,                   -- 13F filer's own SEC CIK
  -- shared external identity
  sec_cik           text,                   -- insider/institution CIK used to hit EDGAR
  metadata          jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT notable_investors_type_check
    CHECK (investor_type IN ('congress', 'insider', 'institution'))
);

CREATE UNIQUE INDEX IF NOT EXISTS notable_investors_congress_uq
  ON notable_investors (bioguide_id) WHERE investor_type = 'congress';
CREATE UNIQUE INDEX IF NOT EXISTS notable_investors_insider_uq
  ON notable_investors (sec_cik, company_cik) WHERE investor_type = 'insider';
CREATE UNIQUE INDEX IF NOT EXISTS notable_investors_institution_uq
  ON notable_investors (manager_cik) WHERE investor_type = 'institution';
CREATE UNIQUE INDEX IF NOT EXISTS notable_investors_slug_uq ON notable_investors (slug);
CREATE INDEX IF NOT EXISTS notable_investors_type_idx ON notable_investors (investor_type, display_name);

CREATE TABLE IF NOT EXISTS notable_investor_trades (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  investor_id         uuid NOT NULL REFERENCES notable_investors(id) ON DELETE CASCADE,
  source              text NOT NULL,        -- senate_stock_watcher | house_stock_watcher | sec_form4 | sec_13f
  ticker              text,                 -- normalized; NULL if unresolved (never dropped for that)
  raw_issuer_name     text,
  cusip               text,                 -- 13F identifies holdings by CUSIP, not ticker
  issuer_cik          text,
  transaction_type    text NOT NULL,        -- buy | sell | exchange | other
  transaction_code    text,                 -- raw Form 4 code (A/D/P/S/...) or source-native type, for audit
  amount_range_min    numeric,              -- Stock Watcher gives a $ range, not an exact amount
  amount_range_max    numeric,
  shares              numeric,
  price_per_share     numeric,
  value_usd           numeric,
  transaction_date    date,
  filed_date          date NOT NULL,
  quarter_end_date    date,                 -- 13F only
  source_url          text,
  source_document_id  text,                 -- accession#:index (SEC) or content hash (Congress)
  raw_payload         jsonb NOT NULL,       -- full original record, for audit/reprocessing
  ingested_at         timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT notable_investor_trades_type_check
    CHECK (transaction_type IN ('buy', 'sell', 'exchange', 'other'))
);

-- Idempotency: every source computes a stable source_document_id so re-syncs
-- upsert rather than duplicate (see the sync modules for how each source
-- derives it — accession#:transaction-index for Form 4, accession#:cusip for
-- 13F, a content hash of member+ticker+date+type+amount for Congress rows).
CREATE UNIQUE INDEX IF NOT EXISTS notable_investor_trades_source_doc_uq
  ON notable_investor_trades (source, source_document_id)
  WHERE source_document_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS notable_investor_trades_ticker_idx
  ON notable_investor_trades (ticker, filed_date DESC) WHERE ticker IS NOT NULL;
CREATE INDEX IF NOT EXISTS notable_investor_trades_investor_idx
  ON notable_investor_trades (investor_id, transaction_date DESC);
CREATE INDEX IF NOT EXISTS notable_investor_trades_filed_date_idx
  ON notable_investor_trades (filed_date DESC);
CREATE INDEX IF NOT EXISTS notable_investor_trades_source_idx
  ON notable_investor_trades (source, filed_date DESC);
CREATE INDEX IF NOT EXISTS notable_investor_trades_unresolved_idx
  ON notable_investor_trades (source, ingested_at) WHERE ticker IS NULL;

-- Per-(source, external key) sync watermark so Form 4 / 13F polling is
-- incremental rather than re-crawling full filing history every run.
CREATE TABLE IF NOT EXISTS notable_investor_sync_state (
  source        text NOT NULL,
  external_key  text NOT NULL,   -- issuer CIK (form4) or filer CIK (13f)
  last_seen_at  text,            -- last accession number or ISO date processed
  updated_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (source, external_key)
);

-- Cache of SEC's company_tickers.json (CIK <-> ticker <-> title), refreshed
-- weekly, backing the ticker/CIK resolver so filings resolve via a DB lookup
-- rather than a live HTTP call per row.
CREATE TABLE IF NOT EXISTS sec_company_tickers (
  cik         text PRIMARY KEY,
  ticker      text NOT NULL,
  title       text,
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sec_company_tickers_ticker_idx ON sec_company_tickers (ticker);

-- Per-user "follow a person" list (mirrors watchlist_items exactly).
CREATE TABLE IF NOT EXISTS notable_investor_follows (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001'
              REFERENCES users(id),
  investor_id uuid NOT NULL REFERENCES notable_investors(id) ON DELETE CASCADE,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, investor_id)
);

CREATE INDEX IF NOT EXISTS idx_notable_investor_follows_user_id ON notable_investor_follows (user_id);
CREATE INDEX IF NOT EXISTS idx_notable_investor_follows_investor_id ON notable_investor_follows (investor_id);

-- Once-per-(user, trade) digest mention marker so a trade is never re-surfaced
-- in a later digest regardless of digest date (mirrors funnel_events' composite-PK idiom).
CREATE TABLE IF NOT EXISTS notable_trade_digest_mentions (
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  trade_id    uuid NOT NULL REFERENCES notable_investor_trades(id) ON DELETE CASCADE,
  surfaced_on date NOT NULL,
  PRIMARY KEY (user_id, trade_id)
);

ALTER TABLE notable_investors ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS notable_investors_app_context ON notable_investors;
CREATE POLICY notable_investors_app_context ON notable_investors
  USING (NULLIF(current_setting('app.current_user_id', true), '') IS NOT NULL);

ALTER TABLE notable_investor_trades ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS notable_investor_trades_app_context ON notable_investor_trades;
CREATE POLICY notable_investor_trades_app_context ON notable_investor_trades
  USING (NULLIF(current_setting('app.current_user_id', true), '') IS NOT NULL);

ALTER TABLE notable_investor_sync_state ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS notable_investor_sync_state_app_context ON notable_investor_sync_state;
CREATE POLICY notable_investor_sync_state_app_context ON notable_investor_sync_state
  USING (NULLIF(current_setting('app.current_user_id', true), '') IS NOT NULL);

ALTER TABLE sec_company_tickers ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS sec_company_tickers_app_context ON sec_company_tickers;
CREATE POLICY sec_company_tickers_app_context ON sec_company_tickers
  USING (NULLIF(current_setting('app.current_user_id', true), '') IS NOT NULL);

ALTER TABLE notable_investor_follows ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS notable_investor_follows_tenant_isolation ON notable_investor_follows;
CREATE POLICY notable_investor_follows_tenant_isolation ON notable_investor_follows
  USING (
    user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
    OR NULLIF(current_setting('app.current_user_id', true), '')::uuid
       = '00000000-0000-0000-0000-000000000001'::uuid
  );

ALTER TABLE notable_trade_digest_mentions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS notable_trade_digest_mentions_tenant_isolation ON notable_trade_digest_mentions;
CREATE POLICY notable_trade_digest_mentions_tenant_isolation ON notable_trade_digest_mentions
  USING (
    user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
    OR NULLIF(current_setting('app.current_user_id', true), '')::uuid
       = '00000000-0000-0000-0000-000000000001'::uuid
  );
