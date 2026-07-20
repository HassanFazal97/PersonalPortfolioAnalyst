-- No-card Pro trial. New signups get trial_ends_at = now() + TRIAL_DAYS (set
-- by the app at provisioning, not by a column default, so the length stays
-- configurable). Semantics:
--   trial_ends_at > now()  and plan='free'  -> full Pro experience
--   trial_ends_at <= now() and plan='free'  -> digests PAUSED until the user
--     chooses: upgrade (webhook sets plan='pro' and clears trial_ends_at) or
--     continue on Free (POST /billing/choose-free clears trial_ends_at).
--   trial_ends_at IS NULL                   -> no trial state; plain plan.
-- Existing users keep NULL (they never had a trial).

ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_ends_at timestamptz;
