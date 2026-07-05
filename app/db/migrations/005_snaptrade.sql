-- Phase 3: per-user SnapTrade credentials (commercial mode).
-- userSecret is stored encrypted (Fernet); app-level CLIENT_ID/CONSUMER_KEY stay in env.

CREATE TABLE IF NOT EXISTS snaptrade_credentials (
  user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  snaptrade_user_id text NOT NULL UNIQUE,
  user_secret_enc bytea NOT NULL,
  connected_at timestamptz,
  last_sync_at timestamptz,
  last_sync_error text,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE snaptrade_credentials ENABLE ROW LEVEL SECURITY;

DO $rls$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'snaptrade_credentials'
      AND policyname = 'snaptrade_credentials_tenant_isolation'
  ) THEN
    CREATE POLICY snaptrade_credentials_tenant_isolation ON snaptrade_credentials
      USING (user_id = current_setting('app.current_user_id', true)::uuid);
  END IF;
END $rls$;
