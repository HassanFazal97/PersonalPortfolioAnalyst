-- Multi-channel notifications (roadmap Phase 5, generalized).
--
-- Users register a destination per channel (sms/email/discord), verify it with
-- a one-time code, and pick a single preferred channel. outbound_messages grows
-- routing columns so the in-process dispatcher can deliver by channel; existing
-- rows backfill to 'imessage' so the Mac worker keeps draining them during the
-- transition. Safe and idempotent, same conventions as 002.

-- 1) Per-user channel registrations -----------------------------------------
CREATE TABLE IF NOT EXISTS notification_channels (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001'
                  REFERENCES users(id),
  channel       text NOT NULL CHECK (channel IN ('sms','email','discord')),
  destination   text NOT NULL,          -- E.164 phone | email address | Discord webhook URL
  verified_at   timestamptz,            -- NULL = destination not yet proven
  consent_at    timestamptz,            -- explicit opt-in timestamp (TCPA for SMS)
  opted_out_at  timestamptz,            -- set by STOP webhook or UI disable
  created_at    timestamptz DEFAULT now(),
  updated_at    timestamptz DEFAULT now(),
  UNIQUE (user_id, channel)
);

-- Reverse lookup for the Twilio STOP/START webhook (phone -> user).
CREATE INDEX IF NOT EXISTS idx_notification_channels_dest
  ON notification_channels (channel, destination);

-- 2) Single preferred channel on users ---------------------------------------
-- NULL = none chosen (delivery skipped, digest stays dashboard-only).
-- 'imessage' is transitional for the owner until the Mac worker retires.
ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_channel text;
DO $nc$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'users_preferred_channel_check'
  ) THEN
    ALTER TABLE users ADD CONSTRAINT users_preferred_channel_check
      CHECK (preferred_channel IN ('sms','email','discord','imessage'));
  END IF;
END $nc$;

-- The owner keeps the current iMessage flow working until cutover.
UPDATE users SET preferred_channel = 'imessage'
  WHERE id = '00000000-0000-0000-0000-000000000001' AND preferred_channel IS NULL;

-- 3) Generalize outbound_messages into a routed delivery queue ---------------
ALTER TABLE outbound_messages
  ADD COLUMN IF NOT EXISTS channel text,
  ADD COLUMN IF NOT EXISTS destination text,          -- snapshot at enqueue time
  ADD COLUMN IF NOT EXISTS payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS last_error text,
  ADD COLUMN IF NOT EXISTS next_attempt_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS provider_message_id text;  -- Twilio SID / Resend id

UPDATE outbound_messages SET channel = 'imessage' WHERE channel IS NULL;

-- Dispatcher poll: due queued rows only.
CREATE INDEX IF NOT EXISTS idx_outbound_due
  ON outbound_messages (status, next_attempt_at) WHERE status = 'queued';

-- 4) One-time verification codes (all channels) -------------------------------
CREATE TABLE IF NOT EXISTS verification_codes (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001'
                 REFERENCES users(id),
  channel      text NOT NULL,
  destination  text NOT NULL,
  code_hash    text NOT NULL,           -- sha256 hex; plaintext never stored
  expires_at   timestamptz NOT NULL,
  attempts     int NOT NULL DEFAULT 0,  -- failed check attempts (max enforced in app)
  consumed_at  timestamptz,
  created_at   timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_verification_codes_user
  ON verification_codes (user_id, channel, created_at);

-- 5) RLS on the new tenant tables (same pattern as 002) -----------------------
DO $nc$
DECLARE tbl text;
BEGIN
  FOREACH tbl IN ARRAY ARRAY['notification_channels','verification_codes']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', tbl || '_tenant_isolation', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING (user_id = NULLIF(current_setting(''app.current_user_id'', true), '''')::uuid)',
      tbl || '_tenant_isolation', tbl
    );
  END LOOP;
END $nc$;
