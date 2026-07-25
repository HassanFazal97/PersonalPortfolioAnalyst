-- Per-user watchlist of arbitrary tickers (need not be held). Presence = the
-- user opted into coverage: news refresh, digest WATCHLIST section, anomaly
-- scans (Pro). Plan-capped at write time in the API (Free 3 / Pro 30).

CREATE TABLE IF NOT EXISTS watchlist_items (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001'
             REFERENCES users(id),
  ticker     text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_items_user_id ON watchlist_items (user_id);

ALTER TABLE watchlist_items ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS watchlist_items_tenant_isolation ON watchlist_items;
CREATE POLICY watchlist_items_tenant_isolation ON watchlist_items
  USING (
    user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
    OR NULLIF(current_setting('app.current_user_id', true), '')::uuid
       = '00000000-0000-0000-0000-000000000001'::uuid
  );
