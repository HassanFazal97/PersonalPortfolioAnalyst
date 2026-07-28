-- Best Stocks pipeline persistence: one row per daily picks run plus one row
-- per pick for the track record. Both are GLOBAL tables (the analysis is
-- market data shared by every Pro user, generated once per day under the
-- owner service context) — same posture as daily_prices/ticker_fundamentals:
-- any app-set GUC may read/write; Data API roles see nothing. Pro gating is
-- enforced at the API route, not in RLS.
--
-- stock_pick_entries deliberately has NO outcome columns: realized returns
-- are computed at read time by joining entry_price (frozen at pick time)
-- against daily_prices, which the universe sync keeps populated. That keeps
-- the track record point-in-time honest with no evaluation job.

CREATE TABLE IF NOT EXISTS stock_picks_runs (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_date             date NOT NULL,
  status               text NOT NULL DEFAULT 'running',  -- running|completed|partial|error
  universe             text NOT NULL,                    -- e.g. 'sp500+tsx60'
  payload              jsonb,                            -- the dashboard document
  stats                jsonb,                            -- coverage/exclusions/verification summary
  run_id               uuid REFERENCES agent_runs(id),   -- anchor run (audit trail)
  cost_usd             numeric,
  methodology_version  int NOT NULL DEFAULT 1,
  created_at           timestamptz NOT NULL DEFAULT now(),
  completed_at         timestamptz
);

CREATE INDEX IF NOT EXISTS stock_picks_runs_date_idx
  ON stock_picks_runs (run_date DESC, created_at DESC);

CREATE TABLE IF NOT EXISTS stock_pick_entries (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  picks_run_id     uuid NOT NULL REFERENCES stock_picks_runs(id) ON DELETE CASCADE,
  run_date         date NOT NULL,
  ticker           text NOT NULL,
  rank             int NOT NULL,
  composite_score  numeric,
  confidence       numeric,
  entry_price      numeric,          -- last stored adjusted close at pick time
  factors          jsonb,
  thesis_summary   text,
  created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS stock_pick_entries_ticker_idx
  ON stock_pick_entries (ticker, run_date);
CREATE INDEX IF NOT EXISTS stock_pick_entries_run_date_idx
  ON stock_pick_entries (run_date DESC);

ALTER TABLE stock_picks_runs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS stock_picks_runs_app_context ON stock_picks_runs;
CREATE POLICY stock_picks_runs_app_context ON stock_picks_runs
  USING (NULLIF(current_setting('app.current_user_id', true), '') IS NOT NULL);

ALTER TABLE stock_pick_entries ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS stock_pick_entries_app_context ON stock_pick_entries;
CREATE POLICY stock_pick_entries_app_context ON stock_pick_entries
  USING (NULLIF(current_setting('app.current_user_id', true), '') IS NOT NULL);
