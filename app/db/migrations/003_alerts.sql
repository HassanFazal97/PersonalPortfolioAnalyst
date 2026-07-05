-- Macro alerts: portfolio-relevant events surfaced by the macro-scan specialists
-- (geopolitical, monetary, energy, regulatory/climate). One row per delivered
-- alert. ``fingerprint`` is a stable hash of the event so a recurring scan does
-- not re-alert the same story; the (user_id, fingerprint) unique makes dedup a
-- property of the schema, not the code.

CREATE TABLE IF NOT EXISTS alerts (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001'
                 REFERENCES users(id),
  run_id       uuid REFERENCES agent_runs(id),
  category     text NOT NULL,              -- geopolitical|monetary|energy|regulatory_climate
  severity     text NOT NULL,              -- low|medium|high
  headline     text NOT NULL,
  body         text NOT NULL,              -- the message delivered to the user
  tickers      jsonb NOT NULL DEFAULT '[]'::jsonb,  -- affected holdings
  fingerprint  text NOT NULL,             -- stable event hash for dedup
  delivered    boolean NOT NULL DEFAULT false,
  delivered_at timestamptz,
  created_at   timestamptz DEFAULT now(),
  UNIQUE (user_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_alerts_user_created ON alerts (user_id, created_at DESC);

-- RLS, consistent with the other tenant tables (owner role bypasses; enforced
-- once a non-owner authenticated role is introduced in roadmap Phase 2).
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS alerts_tenant_isolation ON alerts;
CREATE POLICY alerts_tenant_isolation ON alerts
  USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);
