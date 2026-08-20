-- Forecast ledger: every analytical claim any pipeline publishes (digest,
-- deep dive, picks, macro/anomaly alert) becomes one structured, scoreable
-- row, resolved automatically against daily_prices as its horizon elapses.
-- Generalizes the picks-only track record (023) into a universal ledger and
-- accumulates (context, reasoning trace via run_id, forecast, outcome)
-- tuples for later analysis. Follows 026's append-mostly posture: rows are
-- inserted by the nightly ledger job and only their resolution fields are
-- ever updated; nothing deletes.
--
-- RLS: one table, two postures (034's split, collapsed into one policy):
-- global claims (user_id IS NULL — picks, macro) are readable/writable by
-- any app-set GUC; tenant claims (per-user digests/dives) are visible only
-- to their owner or the owner service context. Data API roles see nothing.

CREATE TABLE IF NOT EXISTS forecasts (
  id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- provenance / flywheel linkage
  run_id                  uuid NOT NULL REFERENCES agent_runs(id),
  user_id                 uuid REFERENCES users(id) ON DELETE CASCADE,  -- NULL = global claim
  source                  text NOT NULL,
  source_ref              uuid,             -- digests.id / deep_dive_reports.id / stock_picks_runs.id / alerts.id
  source_content_hash     text,             -- sha256 of the exact text/JSON the claim was extracted from
  -- the claim itself
  claim_type              text NOT NULL,
  claim_text              text NOT NULL,    -- verbatim quote from the source output
  tickers                 jsonb NOT NULL DEFAULT '[]'::jsonb,
  primary_ticker          text,             -- NULL for market-level claims (benchmark is then the subject)
  benchmark               text,             -- comparison series for relative_performance claims
  direction               text,
  magnitude_min_pct       numeric,          -- only when the author stated one; never invented
  magnitude_max_pct       numeric,
  horizon_days            int NOT NULL,     -- snapped to {7,30,91,182} by the validator
  as_of_date              date NOT NULL,    -- issue date; entry bar = last close STRICTLY BEFORE this
  due_date                date NOT NULL,    -- as_of_date + horizon_days
  confidence_verbal       text NOT NULL,
  probability             numeric,          -- Python-mapped prior (versioned map) or picks' computed confidence
  -- extraction metadata
  extractor               text NOT NULL,    -- deterministic | haiku
  extractor_version       text NOT NULL,
  pipeline_prompt_version text,             -- PROMPT_VERSION of the producing run
  extraction_model        text,
  -- idempotency / restatement grouping
  claim_key               text NOT NULL,    -- hash incl. as_of_date: re-extraction is a no-op
  family_key              text NOT NULL,    -- same hash w/o as_of_date: groups daily restatements
  -- resolution
  status                  text NOT NULL DEFAULT 'open',
  resolved_at             timestamptz,
  outcome                 text,
  realized_value          numeric,          -- realized return pct (drawdown pct for risk_warning)
  benchmark_value         numeric,
  brier                   numeric,
  resolution_detail       jsonb,
  resolver_version        int,
  created_at              timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT forecasts_source_check CHECK
    (source IN ('digest', 'deep_dive', 'picks', 'macro', 'anomaly')),
  CONSTRAINT forecasts_claim_type_check CHECK
    (claim_type IN ('direction', 'relative_performance', 'risk_warning', 'event', 'volatility')),
  CONSTRAINT forecasts_direction_check CHECK
    (direction IS NULL OR direction IN ('up', 'down', 'flat', 'outperform', 'underperform')),
  CONSTRAINT forecasts_confidence_check CHECK
    (confidence_verbal IN ('high', 'medium', 'low', 'speculative')),
  CONSTRAINT forecasts_extractor_check CHECK
    (extractor IN ('deterministic', 'haiku')),
  CONSTRAINT forecasts_status_check CHECK
    (status IN ('open', 'resolved', 'expired', 'invalid')),
  CONSTRAINT forecasts_outcome_check CHECK
    (outcome IS NULL OR outcome IN ('hit', 'miss', 'indeterminate'))
);

CREATE UNIQUE INDEX IF NOT EXISTS forecasts_claim_key_uq ON forecasts (claim_key);
-- The nightly resolver sweep: open rows whose horizon has elapsed.
CREATE INDEX IF NOT EXISTS forecasts_due_open_idx
  ON forecasts (due_date) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS forecasts_family_idx ON forecasts (family_key, as_of_date);
CREATE INDEX IF NOT EXISTS forecasts_source_idx ON forecasts (source, as_of_date DESC);
CREATE INDEX IF NOT EXISTS forecasts_ticker_idx
  ON forecasts (primary_ticker, as_of_date DESC) WHERE primary_ticker IS NOT NULL;

ALTER TABLE forecasts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS forecasts_access ON forecasts;
CREATE POLICY forecasts_access ON forecasts
  USING (
    (user_id IS NULL
     AND NULLIF(current_setting('app.current_user_id', true), '') IS NOT NULL)
    OR user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
    OR NULLIF(current_setting('app.current_user_id', true), '')::uuid
       = '00000000-0000-0000-0000-000000000001'::uuid
  );
