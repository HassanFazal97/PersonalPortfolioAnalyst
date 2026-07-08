-- Retire the transitional iMessage channel (Mac worker deleted).
--
-- Anyone still preferring 'imessage' (the owner, from migration 007) drops to
-- NULL and picks a real channel in the dashboard; queued iMessage rows nobody
-- will ever drain are closed out as failed with an explanatory error.

UPDATE users SET preferred_channel = NULL WHERE preferred_channel = 'imessage';

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_preferred_channel_check;
ALTER TABLE users ADD CONSTRAINT users_preferred_channel_check
  CHECK (preferred_channel IN ('sms','email','discord'));

UPDATE outbound_messages
   SET status = 'failed',
       last_error = 'imessage channel retired (migration 008)'
 WHERE channel = 'imessage' AND status = 'queued';
