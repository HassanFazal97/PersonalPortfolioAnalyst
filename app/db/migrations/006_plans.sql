-- Plans: free vs pro. Gating and per-user cost caps key off this. The owner
-- (user #1) is pro/unlimited. Billing (Stripe) flips this flag later.

ALTER TABLE users ADD COLUMN IF NOT EXISTS plan text NOT NULL DEFAULT 'free';

UPDATE users SET plan = 'pro'
WHERE id = '00000000-0000-0000-0000-000000000001';
