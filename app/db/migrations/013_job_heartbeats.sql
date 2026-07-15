-- Per-job liveness accounting, written by the heartbeat wrapper (app/jobs.py)
-- around each scheduled job (morning_digest, macro_scan, anomaly_scan,
-- delivery_dispatch). Read by GET /health to derive LIVE/DEGRADED/OFFLINE from
-- staleness — turning "the digest silently didn't run this morning" from
-- invisible into detectable. DB-backed (not app.state) so it survives the
-- restarts/redeploys that most often cause jobs to stop firing.

CREATE TABLE IF NOT EXISTS job_heartbeats (
  job_name             text PRIMARY KEY,
  last_attempt_at      timestamptz,
  last_success_at      timestamptz,
  last_error           text,
  consecutive_failures integer NOT NULL DEFAULT 0,
  updated_at           timestamptz DEFAULT now()
);

-- System table, not tenant data: only the service context (GUC = owner id,
-- which background jobs and /health both run under — see migration 012) may
-- touch it. API JWT users can neither read nor write it.
ALTER TABLE job_heartbeats ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS job_heartbeats_service_only ON job_heartbeats;
CREATE POLICY job_heartbeats_service_only ON job_heartbeats
  USING (NULLIF(current_setting('app.current_user_id', true), '')::uuid
         = '00000000-0000-0000-0000-000000000001'::uuid);
