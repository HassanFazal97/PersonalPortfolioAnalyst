-- Global per-ticker daily adjusted-close cache, shared across all tenants
-- (prices are market data, not user data). The quant engine (app/quant/) reads
-- its ~2-year return history from here instead of re-fetching from yfinance on
-- every risk call, which (a) makes risk numbers reproducible across reloads —
-- yfinance silently re-adjusts history, so re-fetching is not deterministic —
-- (b) enables an honest point-in-time VaR backtest, and (c) decouples the
-- request path from Yahoo uptime/rate limits. Populated lazily on read
-- (fill-on-miss) and refreshed by the daily_prices_sync job; see
-- app/tools/price_store.py.
--
-- adj_close is split- and dividend-adjusted (the ONLY series safe for returns;
-- raw close injects spurious split-date jumps). close/currency are nullable
-- forward-compat columns, unpopulated today.

CREATE TABLE IF NOT EXISTS daily_prices (
  ticker      text NOT NULL,
  price_date  date NOT NULL,
  adj_close   numeric NOT NULL,
  close       numeric,
  currency    text,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (ticker, price_date)
);

-- Same posture as ticker_fundamentals (migration 014): the lazy fill-on-miss
-- path writes under whichever user's request context triggered it, so any
-- app-set GUC may read/write. PostgREST/anon callers can never set the GUC
-- (migration 012), so the Data API roles see nothing.
ALTER TABLE daily_prices ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS daily_prices_app_context ON daily_prices;
CREATE POLICY daily_prices_app_context ON daily_prices
  USING (NULLIF(current_setting('app.current_user_id', true), '') IS NOT NULL);
