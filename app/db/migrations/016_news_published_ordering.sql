-- The feed now sorts and filters holding news by publish time, falling back
-- to insert time for rows without one (COALESCE(published_at, created_at)).
-- These expression indexes back that ordering; the old created_at index on
-- (user_id, ticker, created_at) stays for existing queries.

CREATE INDEX IF NOT EXISTS idx_news_items_user_effective
  ON news_items (user_id, (COALESCE(published_at, created_at)) DESC);

CREATE INDEX IF NOT EXISTS idx_news_items_user_ticker_effective
  ON news_items (user_id, ticker, (COALESCE(published_at, created_at)) DESC);
