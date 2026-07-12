-- Production runs the app on a non-owner role (DATABASE_URL restricted,
-- MIGRATION_DATABASE_URL owner), so the tenant policies are ENFORCED, not
-- dormant as previously assumed. Two things break under strict per-tenant
-- policies:
--
--   1. Auth-time provisioning: get_or_create_user runs BEFORE the request
--      user is bound, so the GUC falls back to the owner id — it must look
--      up users by auth_id and insert rows whose id is not the GUC. After
--      011 this 500'd every JWT request ("violates row-level security
--      policy for table users").
--   2. Service fan-out: schedulers list recipients across all tenants
--      (users, positions) with the owner GUC before binding each user.
--
-- Fix: treat GUC = owner id as the service context and let it cross
-- tenants. Only the app can set the GUC (the Supabase Data API offers no
-- way to set arbitrary GUCs), so anon/authenticated API callers still see
-- nothing. schema_migrations stays deny-all.

DO $svc$
DECLARE
  owner_esc constant text :=
    'NULLIF(current_setting(''app.current_user_id'', true), '''')::uuid';
  owner_id constant text := '''00000000-0000-0000-0000-000000000001''::uuid';
  tbl text;
BEGIN
  -- Tables with a user_id column.
  FOREACH tbl IN ARRAY ARRAY[
    'positions', 'transactions', 'agent_runs', 'digests',
    'outbound_messages', 'alerts', 'notification_channels',
    'verification_codes', 'news_items', 'snaptrade_credentials'
  ]
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', tbl || '_tenant_isolation', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING (user_id = %s OR %s = %s)',
      tbl || '_tenant_isolation', tbl, owner_esc, owner_esc, owner_id
    );
  END LOOP;

  -- users: the tenant id is the PK itself.
  EXECUTE 'DROP POLICY IF EXISTS users_tenant_isolation ON users';
  EXECUTE format(
    'CREATE POLICY users_tenant_isolation ON users USING (id = %s OR %s = %s)',
    owner_esc, owner_esc, owner_id
  );

  -- model_calls / tool_calls: tenancy via their run.
  FOREACH tbl IN ARRAY ARRAY['model_calls', 'tool_calls']
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', tbl || '_tenant_isolation', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING ('
      '  EXISTS (SELECT 1 FROM agent_runs r WHERE r.id = run_id AND r.user_id = %s)'
      '  OR %s = %s'
      ')',
      tbl || '_tenant_isolation', tbl, owner_esc, owner_esc, owner_id
    );
  END LOOP;
END $svc$;
