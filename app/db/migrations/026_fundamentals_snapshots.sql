-- Point-in-time fundamentals, by construction. ticker_fundamentals (014) is a
-- latest-only cache — every refresh overwrites, so nothing can prove what the
-- screener saw on a past date, and yfinance revises fields silently
-- (look-ahead/revision bias, the audit's biggest criticism of the picks
-- screen). Historical PIT data costs institutional money; PIT going forward
-- costs one nightly INSERT: the evening universe sync appends a dated copy of
-- each ticker's payload here and NOTHING ever updates or deletes rows. From
-- the first snapshot onward, every pick can be re-derived from data
-- timestamped before the pick.
--
-- payload_hash (sha256 of the canonical payload JSON) makes rows cheap to
-- compare/dedupe downstream and tamper-evident in audits.

CREATE TABLE IF NOT EXISTS fundamentals_snapshots (
  ticker        text NOT NULL,
  snapshot_date date NOT NULL,
  payload       jsonb NOT NULL,
  payload_hash  text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (ticker, snapshot_date)
);

-- "As it would have run on date D" reads resolve per ticker to the latest
-- snapshot <= D; the PK covers (ticker, snapshot_date) lookups already, and
-- this index serves whole-universe-by-date scans.
CREATE INDEX IF NOT EXISTS idx_fundamentals_snapshots_date
  ON fundamentals_snapshots (snapshot_date);

-- Same app-context posture as daily_prices (020): written under whichever
-- context runs the sync job, read by owner-context tooling; Data API roles
-- can never set the GUC.
ALTER TABLE fundamentals_snapshots ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS fundamentals_snapshots_app_context ON fundamentals_snapshots;
CREATE POLICY fundamentals_snapshots_app_context ON fundamentals_snapshots
  USING (NULLIF(current_setting('app.current_user_id', true), '') IS NOT NULL);
