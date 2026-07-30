-- Universe membership history. The static generated constituent list
-- (app/tools/universe_constituents.py) says who is in the universe TODAY;
-- it cannot say who was in it when a past pick was made, which bakes
-- survivorship bias into any backward-looking analysis. This table records
-- membership as dated intervals: the evening sync diffs the deployed list
-- against the open intervals and appends additions / closes removals, so
-- history accrues by construction. Removed names are never deleted — a
-- delisted pick keeps its rows (and its prices keep syncing while any pick
-- entry references it), so blown-up picks show their real loss instead of
-- silently vanishing.

CREATE TABLE IF NOT EXISTS universe_membership (
  ticker     text NOT NULL,
  universe   text NOT NULL,          -- e.g. 'sp500' | 'tsx60'
  added_at   date NOT NULL,
  removed_at date,                   -- NULL = currently a member
  PRIMARY KEY (ticker, universe, added_at)
);

CREATE INDEX IF NOT EXISTS idx_universe_membership_active
  ON universe_membership (universe) WHERE removed_at IS NULL;

-- App-context posture, as with daily_prices (020).
ALTER TABLE universe_membership ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS universe_membership_app_context ON universe_membership;
CREATE POLICY universe_membership_app_context ON universe_membership
  USING (NULLIF(current_setting('app.current_user_id', true), '') IS NOT NULL);
