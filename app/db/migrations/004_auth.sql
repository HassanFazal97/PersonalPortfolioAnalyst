-- Phase 2 auth: link app users to their Supabase Auth identity.
--
-- ``auth_id`` is the Supabase ``auth.users`` uuid (the JWT ``sub``). A new app
-- user row is provisioned on first authenticated request. The existing owner
-- (user #1) keeps auth_id NULL until you link it to your own Supabase account
-- (UPDATE users SET auth_id = '<your-supabase-uid>' WHERE id =
-- '00000000-0000-0000-0000-000000000001';).

ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_id uuid;

DO $auth$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'users_auth_id_key'
  ) THEN
    ALTER TABLE users ADD CONSTRAINT users_auth_id_key UNIQUE (auth_id);
  END IF;
END $auth$;
