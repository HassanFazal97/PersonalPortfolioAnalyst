-- Registered devices for push notifications (native app).
--
-- Push is a fan-out, not a fourth preferred_channel. `users.preferred_channel`
-- resolves ONE destination and enqueue_outbound writes ONE row; if push were
-- selectable there, choosing it would silently take away the user's email
-- digest -- and a ~4KB push payload cannot carry a digest anyway. Push is a
-- pointer to content, so it writes one additional outbound_messages row per
-- registered device, alongside whatever the preferred channel does.
--
-- outbound_messages.channel is a plain text column with no CHECK constraint
-- (007), so channel='push' needs no constraint change.

CREATE TABLE IF NOT EXISTS push_devices (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- UNIQUE on the token alone, deliberately NOT (user_id, expo_token): a
  -- shared or resold phone that signs into a second account must MOVE the
  -- token to that account, not end up delivering one device's push to two
  -- people. The upsert re-points user_id on conflict.
  expo_token   text NOT NULL UNIQUE,
  platform     text NOT NULL DEFAULT 'ios',
  -- Which notification kinds this device wants; the fan-out filters on it.
  -- jsonb rather than text[], matching users.digest_tickers (004).
  kinds        jsonb NOT NULL DEFAULT '["digest","alert","deep_dive"]'::jsonb,
  -- Set when Expo reports DeviceNotRegistered. Kept rather than deleted so a
  -- reinstall re-registering the same token is a visible reactivation.
  disabled_at  timestamptz,
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- The fan-out's only read: active devices for one user.
CREATE INDEX IF NOT EXISTS idx_push_devices_user
  ON push_devices (user_id) WHERE disabled_at IS NULL;

-- RLS, same tenant-isolation pattern as 007's notification_channels.
DO $pd$
BEGIN
  EXECUTE 'ALTER TABLE push_devices ENABLE ROW LEVEL SECURITY';
  EXECUTE 'DROP POLICY IF EXISTS push_devices_tenant_isolation ON push_devices';
  EXECUTE
    'CREATE POLICY push_devices_tenant_isolation ON push_devices '
    'USING (user_id = NULLIF(current_setting(''app.current_user_id'', true), '''')::uuid)';
END $pd$;
