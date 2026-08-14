-- Indexes for the hot read paths surfaced by the latency audit. Each one
-- serves a query that today scans or sorts every row for the user (or, for
-- positions.ticker and the FK indexes, the whole table).

-- Chat quota: runs on EVERY /me — count + min(created_at) of non-error chat
-- runs in the rolling window (app/db/repo.py::chat_usage_since).
CREATE INDEX IF NOT EXISTS idx_agent_runs_chat_quota
  ON agent_runs (user_id, trigger, created_at DESC)
  WHERE status <> 'error';

-- list_recent_digests sorts every digest row the user has.
CREATE INDEX IF NOT EXISTS idx_digests_user_created
  ON digests (user_id, created_at DESC);

-- Unindexed FK: every picks-run parent delete seq-scans the entries.
CREATE INDEX IF NOT EXISTS idx_stock_pick_entries_run
  ON stock_pick_entries (picks_run_id);

-- (fundamentals_snapshots needs nothing: its PRIMARY KEY (ticker,
-- snapshot_date) already serves latest-first per-ticker reads.)

-- Unindexed FK on news_items.run_id.
CREATE INDEX IF NOT EXISTS idx_news_items_run
  ON news_items (run_id);

-- The nightly jobs take DISTINCT ticker across ALL positions (global by
-- design — one scan per ticker, not per user); a ticker index turns that
-- from a growing full-table scan into an index-only skip.
CREATE INDEX IF NOT EXISTS idx_positions_ticker
  ON positions (ticker);
