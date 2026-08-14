-- Account-deletion tombstones.
--
-- DELETE /me removes every app row a user owns, but the Supabase JWT they are
-- still holding stays cryptographically valid until its own exp (~1h): deleting
-- the Supabase auth user stops NEW tokens being issued, it cannot revoke the
-- ones already out there. Without a tombstone the next request carrying that
-- token walks straight into get_or_create_user and silently provisions a fresh
-- empty account for someone who just deleted theirs -- and a fresh no-card
-- trial with it, the next time they sync a portfolio.
--
-- The tombstone records when the account was deleted; provisioning refuses any
-- token issued (iat) at or before that instant. A genuine later sign-in --
-- which stays possible when the Supabase auth user outlives the delete, e.g.
-- no service-role key is configured -- carries a newer iat, clears the
-- tombstone, and provisions normally. That is why this is not a permanent
-- ban list: a permanent one would lock such a user out for good.

CREATE TABLE IF NOT EXISTS deleted_auth_ids (
  auth_id    uuid PRIMARY KEY,
  deleted_at timestamptz NOT NULL DEFAULT now()
);

-- RLS mirrors ticker_fundamentals (014) rather than the service-only policies
-- (013, 015), because the two ends run under different contexts: the tombstone
-- is WRITTEN by DELETE /me bound as the departing user, and READ during
-- provisioning, which runs before any user is bound and so falls back to the
-- owner GUC (see 012). Any app-set GUC may therefore read/write. PostgREST
-- callers can never set the GUC, so anon/authenticated Data API roles still
-- see nothing. The table holds opaque auth uids and timestamps -- no personal
-- data, nothing that identifies a person on its own.
ALTER TABLE deleted_auth_ids ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS deleted_auth_ids_app_context ON deleted_auth_ids;
CREATE POLICY deleted_auth_ids_app_context ON deleted_auth_ids
  USING (NULLIF(current_setting('app.current_user_id', true), '') IS NOT NULL);
