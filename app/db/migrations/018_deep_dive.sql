-- Portfolio Deep Dive: multi-agent research reports (plan -> parallel
-- specialists -> critic -> synthesize; see app/agent/deep_dive/). One row per
-- run. ``report`` is the structured JSON the dashboard renders; ``summary`` is
-- the short deliverable text for SMS/email; ``progress`` is a stage snapshot
-- so a reconnecting browser can rehydrate the progress UI without event
-- replay. Not merged into ``digests``: different shape (structured vs prose),
-- different lifecycle (running|completed|partial|error vs one-per-day upsert).

CREATE TABLE IF NOT EXISTS deep_dive_reports (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001'
                 REFERENCES users(id),
  run_id       uuid NOT NULL REFERENCES agent_runs(id),   -- anchor run
  status       text NOT NULL DEFAULT 'running',           -- running|completed|partial|error
  report       jsonb,
  summary      text,
  progress     jsonb NOT NULL DEFAULT '{}'::jsonb,
  cost_usd     numeric,
  created_at   timestamptz DEFAULT now(),
  completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_deep_dive_reports_user_created
  ON deep_dive_reports (user_id, created_at DESC);

-- RLS: tenant isolation with the owner-service-context escape (migration 012
-- pattern) so scheduled fan-out and owner tooling can cross tenants while an
-- authenticated user only ever sees their own reports.
ALTER TABLE deep_dive_reports ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS deep_dive_reports_tenant_isolation ON deep_dive_reports;
CREATE POLICY deep_dive_reports_tenant_isolation ON deep_dive_reports
  USING (
    user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
    OR NULLIF(current_setting('app.current_user_id', true), '')::uuid
       = '00000000-0000-0000-0000-000000000001'::uuid
  );
