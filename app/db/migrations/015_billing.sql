-- Stripe billing: customer/subscription linkage on users, plus a webhook
-- event ledger for idempotent processing. Only what the UI and ops need
-- without a live Stripe call is mirrored here; invoices, payment methods,
-- and dunning state stay in Stripe (surfaced via the Customer Portal).

ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_subscription_id text;
-- When the user last became pro (audit; cleared implies never upgraded).
ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_since timestamptz;
-- Renders "Pro until <date>" in settings without a Stripe round-trip.
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_current_period_end timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_cancel_at_period_end boolean NOT NULL DEFAULT false;

-- Webhooks map customer -> user; partial unique also guards against two
-- users ever sharing a Stripe customer.
CREATE UNIQUE INDEX IF NOT EXISTS users_stripe_customer_id_key
  ON users (stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;

-- Webhook idempotency ledger: one row per processed Stripe event (id + type
-- only, no payload/PII — the Stripe dashboard keeps the full event).
CREATE TABLE IF NOT EXISTS stripe_events (
  id          text PRIMARY KEY,
  type        text NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now()
);

-- RLS: without it the anon Data API could read/write this table (see 011).
-- Unlike schema_migrations, the app's restricted role writes here at runtime
-- (webhook handler runs unbound => GUC = owner id, the service context of
-- migration 012), so deny-all is wrong — allow exactly that context.
ALTER TABLE stripe_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS stripe_events_service ON stripe_events;
CREATE POLICY stripe_events_service ON stripe_events
  USING (NULLIF(current_setting('app.current_user_id', true), '')::uuid
         = '00000000-0000-0000-0000-000000000001'::uuid)
  WITH CHECK (NULLIF(current_setting('app.current_user_id', true), '')::uuid
         = '00000000-0000-0000-0000-000000000001'::uuid);
