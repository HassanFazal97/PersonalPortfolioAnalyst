-- Global per-ticker fundamentals cache: one yfinance .info snapshot (plus
-- derived metrics) per ticker, shared across all tenants — fundamentals are
-- market data, not user data, so two users holding NVDA share one fetch.
-- Refreshed nightly by the fundamentals_refresh job and lazily on read
-- (stale-while-revalidate); see app/tools/fundamentals.py. fetch_error marks
-- tickers yfinance can't serve (crypto, delisted) so they retry on a short
-- TTL instead of hammering Yahoo on every page load.

CREATE TABLE IF NOT EXISTS ticker_fundamentals (
  ticker      text PRIMARY KEY,
  quote_type  text,
  data        jsonb NOT NULL DEFAULT '{}'::jsonb,
  fetched_at  timestamptz NOT NULL DEFAULT now(),
  fetch_error text
);

-- Not service-only like job_heartbeats: the lazy-refresh path writes under
-- whichever user's request context triggered it, so any app-set GUC may
-- read/write. PostgREST callers can never set the GUC (see migration 012),
-- so anon/authenticated Data API roles see nothing.
ALTER TABLE ticker_fundamentals ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ticker_fundamentals_app_context ON ticker_fundamentals;
CREATE POLICY ticker_fundamentals_app_context ON ticker_fundamentals
  USING (NULLIF(current_setting('app.current_user_id', true), '') IS NOT NULL);
