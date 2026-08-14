-- Post-onboarding product tour (dashboard coach-mark overlay). NULL = the
-- user has never seen the tour; set when they finish OR skip it, so it shows
-- at most once per account across devices. Existing users stay NULL and are
-- never auto-toured (the welcome-flow gate requires ?welcome=1) — they can
-- replay it from Settings. Pure overlay state: must never influence routing.

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS tutorial_completed_at timestamptz;
