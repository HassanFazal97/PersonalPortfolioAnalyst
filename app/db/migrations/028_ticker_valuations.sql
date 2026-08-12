-- Global per-ticker valuation verdict cache: one row per ticker, latest
-- computed verdict only (like ticker_fundamentals, migration 014 -- not
-- point-in-time like fundamentals_snapshots, migration 026). Written once
-- daily by the valuation_refresh job (app/tools/valuation_refresh.py) from
-- app/quant/valuation.py::compute_valuations(), which is pure math over
-- already-fresh ticker_fundamentals/daily_prices -- this table just caches
-- the result so /stocks/valuations and the per-ticker verdict block are flat
-- reads, never live numpy per request.
--
-- verdict is sector-relative only (see app/quant/valuation.py docstring for
-- why "own 10-year history" isn't measured yet); sector_z/metrics_used/
-- sector_comparison/evidence are the "show your work" numbers behind it.
-- not_scored_reason carries the excluded-ticker reason string when verdict
-- is 'Not enough data' -- mirrors the screener's "excluded always carries a
-- reason" convention (app/quant/screener.py).

CREATE TABLE IF NOT EXISTS ticker_valuations (
  ticker             text PRIMARY KEY,
  as_of              date NOT NULL,
  verdict            text NOT NULL,
  sector_z           numeric,
  metrics_used       integer NOT NULL DEFAULT 0,
  sector             text,
  sector_comparison  text,
  name               text,
  market_cap         numeric,
  last_price         numeric,
  evidence           jsonb,
  not_scored_reason  text,
  updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ticker_valuations_verdict
  ON ticker_valuations (verdict);

-- Same posture as ticker_fundamentals (014) / daily_prices (020): written
-- under the owner/service context that runs the nightly job, read by both
-- app-context callers and the public (auth-exempt) /stocks/valuations route
-- at the FastAPI layer -- PostgREST/anon Data API roles can never set the
-- GUC (migration 012), so this RLS posture doesn't itself make the table
-- public; the app route does that deliberately.
ALTER TABLE ticker_valuations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ticker_valuations_app_context ON ticker_valuations;
CREATE POLICY ticker_valuations_app_context ON ticker_valuations
  USING (NULLIF(current_setting('app.current_user_id', true), '') IS NOT NULL);
