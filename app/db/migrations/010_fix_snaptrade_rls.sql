-- Align the snaptrade_credentials RLS policy with every other tenant policy
-- (002/003/007/009): NULLIF guards the empty-string GUC so an unset user
-- context means deny-all instead of "invalid input syntax for type uuid".
-- NOTE (added later): production already runs the app on a non-owner role,
-- so this policy is enforced, not dormant. Superseded by 012, which adds
-- the owner service-context escape to every tenant policy.

DROP POLICY IF EXISTS snaptrade_credentials_tenant_isolation ON snaptrade_credentials;

CREATE POLICY snaptrade_credentials_tenant_isolation ON snaptrade_credentials
  USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);
