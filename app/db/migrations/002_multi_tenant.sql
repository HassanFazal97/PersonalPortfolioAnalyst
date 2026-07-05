-- Multi-tenant foundation (roadmap Phase 1).
--
-- Adds a users table and a user_id on every tenant-scoped table, backfilling all
-- existing rows to the single owner (user #1) so this is a safe, idempotent
-- upgrade of the running single-user deployment. Uniques become per-user. RLS is
-- enabled with per-user policies, but the app currently connects as the table
-- owner (which bypasses RLS); the policies take effect once per-user auth
-- (roadmap Phase 2) connects as a non-owner role and sets app.current_user_id.

CREATE TABLE IF NOT EXISTS users (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email            text UNIQUE,
  timezone         text NOT NULL DEFAULT 'America/Toronto',   -- IANA name
  digest_send_time time NOT NULL DEFAULT '07:45',
  digest_enabled   boolean NOT NULL DEFAULT true,
  created_at       timestamptz DEFAULT now()
);

-- The single existing owner becomes user #1 with a fixed id so backfills and the
-- app's default_user_id stay stable across environments.
INSERT INTO users (id, email)
VALUES ('00000000-0000-0000-0000-000000000001', 'owner@localhost')
ON CONFLICT (id) DO NOTHING;

-- Add user_id (nullable), backfill to the owner, then enforce NOT NULL + FK +
-- index. Looped so the pattern is written once; each step guards against re-run.
DO $mt$
DECLARE
  owner uuid := '00000000-0000-0000-0000-000000000001';
  tbl   text;
BEGIN
  FOREACH tbl IN ARRAY ARRAY['positions','transactions','agent_runs','digests','outbound_messages']
  LOOP
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS user_id uuid', tbl);
    EXECUTE format('UPDATE %I SET user_id = %L WHERE user_id IS NULL', tbl, owner);
    EXECUTE format('ALTER TABLE %I ALTER COLUMN user_id SET NOT NULL', tbl);
    EXECUTE format('ALTER TABLE %I ALTER COLUMN user_id SET DEFAULT %L', tbl, owner);
    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint WHERE conname = tbl || '_user_id_fkey'
    ) THEN
      EXECUTE format(
        'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (user_id) REFERENCES users(id)',
        tbl, tbl || '_user_id_fkey'
      );
    END IF;
    EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I (user_id)', 'idx_' || tbl || '_user_id', tbl);
  END LOOP;
END $mt$;

-- Swap single-tenant uniques for per-user ones.
ALTER TABLE positions DROP CONSTRAINT IF EXISTS positions_ticker_account_key;
ALTER TABLE positions ADD CONSTRAINT positions_user_ticker_account_key
  UNIQUE (user_id, ticker, account);

ALTER TABLE digests DROP CONSTRAINT IF EXISTS digests_digest_date_key;
ALTER TABLE digests ADD CONSTRAINT digests_user_digest_date_key
  UNIQUE (user_id, digest_date);

-- Row-Level Security. Policies scope every tenant table by user_id, resolved
-- from a request-scoped GUC. The table owner bypasses RLS, so the app keeps
-- working today; enforcement kicks in when a non-owner authenticated role is
-- introduced in Phase 2.
DO $mt$
DECLARE tbl text;
BEGIN
  FOREACH tbl IN ARRAY ARRAY['positions','transactions','agent_runs','digests','outbound_messages']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', tbl || '_tenant_isolation', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING (user_id = NULLIF(current_setting(''app.current_user_id'', true), '''')::uuid)',
      tbl || '_tenant_isolation', tbl
    );
  END LOOP;
END $mt$;
