-- Free-tier digest watchlist + persisted holding-specific news from digests.

ALTER TABLE users ADD COLUMN IF NOT EXISTS digest_tickers jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS news_items (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001'
                 REFERENCES users(id),
  ticker       text NOT NULL,
  headline     text NOT NULL,
  source       text,
  url          text,
  published_at timestamptz,
  summary      text,
  run_id       uuid REFERENCES agent_runs(id),
  fingerprint  text NOT NULL,
  created_at   timestamptz DEFAULT now(),
  UNIQUE (user_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_news_items_user_ticker
  ON news_items (user_id, ticker, created_at DESC);

ALTER TABLE news_items ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS news_items_tenant_isolation ON news_items;
CREATE POLICY news_items_tenant_isolation ON news_items
  USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);
