-- Server-side funnel milestones (signup -> connected -> trial -> decision).
-- The roadmap gates decisions on these measurements (activation fixes, the
-- ~50-paying-users quant gate), so they must be queryable, not just lines in
-- the cirvia.funnel log stream that Railway rotates away.
--
-- One row per (user, event): these are once-per-account milestones, enforced
-- by the primary key so recording is idempotent (ON CONFLICT DO NOTHING).
-- Repeatable behaviour (chat, digests, picks views) already lives in
-- agent_runs/digests and does not belong here.

CREATE TABLE IF NOT EXISTS funnel_events (
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event       text NOT NULL,
  meta        jsonb NOT NULL DEFAULT '{}',
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, event)
);

CREATE INDEX IF NOT EXISTS idx_funnel_events_event_created
  ON funnel_events (event, created_at);

-- Same app-context posture as daily_prices (020): rows are written under
-- whichever user's request triggered the milestone and read only by
-- owner-context analytics; Data API roles can never set the GUC.
ALTER TABLE funnel_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS funnel_events_app_context ON funnel_events;
CREATE POLICY funnel_events_app_context ON funnel_events
  USING (NULLIF(current_setting('app.current_user_id', true), '') IS NOT NULL);
