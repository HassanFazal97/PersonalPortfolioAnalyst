-- Trial clock starts at the first value moment (first successful portfolio
-- sync), not at signup: a user who signs up Monday and connects Friday should
-- get all 7 Pro days, not 2. trial_started_at records that the account's one
-- trial has been consumed — trial_ends_at can't carry that fact because both
-- resolutions (upgrade webhook, choose-free) clear it, and re-arming a trial
-- on reconnect would make trials infinite.
ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_started_at timestamptz;

-- Every pre-existing account had its trial armed at signup (the old
-- semantics), so mark them all consumed; only accounts created after this
-- migration arm at first sync.
UPDATE users SET trial_started_at = COALESCE(created_at, now())
WHERE trial_started_at IS NULL;
