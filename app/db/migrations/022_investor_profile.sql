-- Investor profile: traits captured during onboarding drive per-user
-- personalization of digests, news selection, deep dives, and chat framing.
-- The archetype is a derived label (see app/profile.py::derive_archetype);
-- traits are the source of truth. All columns NULL/[] for existing users =
-- "not profiled" — code substitutes DEFAULT_PROFILE (long_term_growth, 5/10,
-- 'years'), so behavior is unchanged until a user completes profiling.
-- profile_prompt_dismissed_at persists the one-time "Personalize your
-- experience" dashboard prompt dismissal across devices.

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS investor_archetype text
      CHECK (investor_archetype IS NULL OR investor_archetype IN
             ('day_trader','swing_trader','long_term_growth','income_preservation')),
  ADD COLUMN IF NOT EXISTS risk_tolerance smallint
      CHECK (risk_tolerance IS NULL OR risk_tolerance BETWEEN 1 AND 10),
  ADD COLUMN IF NOT EXISTS investing_horizon text
      CHECK (investing_horizon IS NULL OR investing_horizon IN
             ('days','weeks_months','years','decade_plus')),
  ADD COLUMN IF NOT EXISTS investing_experience text
      CHECK (investing_experience IS NULL OR investing_experience IN
             ('new','lt_1y','1_5y','5_10y','10y_plus')),
  ADD COLUMN IF NOT EXISTS investing_goals jsonb NOT NULL DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS profile_completed_at timestamptz,
  ADD COLUMN IF NOT EXISTS profile_prompt_dismissed_at timestamptz;
