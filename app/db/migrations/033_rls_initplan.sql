-- Rewrap every RLS policy's GUC read in a scalar subquery:
--
--   NULLIF(current_setting('app.current_user_id', true), '')::uuid
--   -> (SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid)
--
-- Postgres then evaluates it once per statement (an InitPlan constant) and
-- can push `user_id = <const>` into an index scan, instead of calling
-- current_setting() per candidate row. Standard Supabase RLS guidance.
--
-- Every predicate below is semantically IDENTICAL to the one it replaces
-- (012, 013, 018, 019, 021, 023, 025-030) — only the evaluation shape
-- changes. push_devices keeps its deliberate lack of an owner-service
-- escape; job_heartbeats stays service-only; the *_app_context tables stay
-- readable to any bound app context. Verified end-to-end by
-- tests/test_rls_policies.py (requires Docker).

DO $ip$
DECLARE
  guc constant text :=
    '(SELECT NULLIF(current_setting(''app.current_user_id'', true), '''')::uuid)';
  guc_txt constant text :=
    '(SELECT NULLIF(current_setting(''app.current_user_id'', true), ''''))';
  owner_id constant text := '''00000000-0000-0000-0000-000000000001''::uuid';
  tbl text;
BEGIN
  -- Tenant rows + owner-service escape (the 012/018/019/021 shape).
  FOREACH tbl IN ARRAY ARRAY[
    'positions', 'transactions', 'agent_runs', 'digests',
    'outbound_messages', 'alerts', 'notification_channels',
    'verification_codes', 'news_items', 'snaptrade_credentials',
    'deep_dive_reports', 'memory_chunks', 'watchlist_items'
  ]
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', tbl || '_tenant_isolation', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING (user_id = %s OR %s = %s)',
      tbl || '_tenant_isolation', tbl, guc, guc, owner_id
    );
  END LOOP;

  -- users: the tenant id is the PK itself.
  EXECUTE 'DROP POLICY IF EXISTS users_tenant_isolation ON users';
  EXECUTE format(
    'CREATE POLICY users_tenant_isolation ON users USING (id = %s OR %s = %s)',
    guc, guc, owner_id
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
      tbl || '_tenant_isolation', tbl, guc, guc, owner_id
    );
  END LOOP;

  -- push_devices: tenant-only, deliberately NO owner-service escape (030).
  EXECUTE 'DROP POLICY IF EXISTS push_devices_tenant_isolation ON push_devices';
  EXECUTE format(
    'CREATE POLICY push_devices_tenant_isolation ON push_devices USING (user_id = %s)',
    guc
  );

  -- Shared reference tables: readable to any bound app context.
  FOREACH tbl IN ARRAY ARRAY[
    'ticker_fundamentals', 'daily_prices', 'stock_picks_runs',
    'stock_pick_entries', 'funnel_events', 'universe_membership',
    'fundamentals_snapshots', 'ticker_valuations', 'deleted_auth_ids'
  ]
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', tbl || '_app_context', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING (%s IS NOT NULL)',
      tbl || '_app_context', tbl, guc_txt
    );
  END LOOP;

  -- job_heartbeats: service context only (013).
  EXECUTE 'DROP POLICY IF EXISTS job_heartbeats_service_only ON job_heartbeats';
  EXECUTE format(
    'CREATE POLICY job_heartbeats_service_only ON job_heartbeats USING (%s = %s)',
    guc, owner_id
  );
END $ip$;
