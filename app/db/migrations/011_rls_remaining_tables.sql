-- Enable RLS on the four tables the earlier migrations skipped: users,
-- model_calls, tool_calls, and schema_migrations. These show as
-- "Unrestricted" in the Supabase dashboard, and — more importantly — the
-- auto-generated Data API (PostgREST) serves the public schema to anyone
-- holding the anon key, with RLS as the only gate. RLS-less tables there
-- are world-readable/writable. The app itself is unaffected: it connects
-- as the table owner, which bypasses RLS (until Phase 2's non-owner role).

-- users: a user may only see their own row. PK is the tenant id itself.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS users_tenant_isolation ON users;
CREATE POLICY users_tenant_isolation ON users
  USING (id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

-- model_calls / tool_calls carry no user_id; tenancy comes from their run.
-- The EXISTS probe is agent_runs' PK lookup, so Phase 2 reads stay cheap.
DO $rls$
DECLARE tbl text;
BEGIN
  FOREACH tbl IN ARRAY ARRAY['model_calls', 'tool_calls']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', tbl || '_tenant_isolation', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING (EXISTS ('
      '  SELECT 1 FROM agent_runs r WHERE r.id = run_id'
      '  AND r.user_id = NULLIF(current_setting(''app.current_user_id'', true), '''')::uuid'
      '))',
      tbl || '_tenant_isolation', tbl
    );
  END LOOP;
END $rls$;

-- schema_migrations: only the (owner) migration runner touches it — no
-- policy at all, so RLS-subject roles are denied everything.
ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY;
