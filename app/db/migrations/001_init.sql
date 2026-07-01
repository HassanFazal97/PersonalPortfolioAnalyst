CREATE TABLE positions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker      text NOT NULL,               -- Yahoo format
  quantity    numeric NOT NULL,
  avg_cost    numeric NOT NULL,            -- per share, position currency
  currency    text NOT NULL DEFAULT 'CAD',
  account     text NOT NULL,               -- 'TFSA' | 'RRSP' | 'taxable'
  updated_at  timestamptz DEFAULT now(),
  UNIQUE (ticker, account)
);

CREATE TABLE transactions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker      text NOT NULL,
  side        text NOT NULL CHECK (side IN ('buy','sell')),
  quantity    numeric NOT NULL,
  price       numeric NOT NULL,
  fees        numeric DEFAULT 0,
  account     text NOT NULL,
  executed_at timestamptz NOT NULL
);

CREATE TABLE agent_runs (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trigger        text NOT NULL,            -- 'chat' | 'digest'
  user_message   text NOT NULL,
  final_answer   text,
  status         text NOT NULL DEFAULT 'running',
                 -- running|completed|budget_exceeded|max_iterations|error
  iterations     int,
  input_tokens   int,
  output_tokens  int,
  cost_usd       numeric,
  latency_ms     int,
  model          text NOT NULL,
  prompt_version text NOT NULL,
  error_detail   text,
  created_at     timestamptz DEFAULT now()
);

CREATE TABLE model_calls (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id     uuid NOT NULL REFERENCES agent_runs(id),
  iteration  int NOT NULL,
  request    jsonb NOT NULL,               -- full request body sent
  response   jsonb NOT NULL,               -- full response content
  usage      jsonb NOT NULL,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE tool_calls (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id     uuid NOT NULL REFERENCES agent_runs(id),
  iteration  int NOT NULL,
  tool_name  text NOT NULL,
  input      jsonb NOT NULL,
  output     jsonb,
  is_error   boolean DEFAULT false,
  latency_ms int,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE digests (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id       uuid NOT NULL REFERENCES agent_runs(id),
  body         text NOT NULL,              -- final text, <= 900 chars
  digest_date  date NOT NULL UNIQUE,       -- America/Toronto date
  delivered    boolean DEFAULT false,
  delivered_at timestamptz,
  delivery_channel text,                   -- 'shortcuts' | 'imessage'
  created_at   timestamptz DEFAULT now()
);

CREATE TABLE outbound_messages (            -- Phase B queue for Mac worker
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  body       text NOT NULL,
  status     text NOT NULL DEFAULT 'queued', -- queued|sent|failed
  attempts   int DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  sent_at    timestamptz
);

CREATE INDEX ON model_calls (run_id);
CREATE INDEX ON tool_calls (run_id);
CREATE INDEX ON agent_runs (trigger, created_at DESC);
