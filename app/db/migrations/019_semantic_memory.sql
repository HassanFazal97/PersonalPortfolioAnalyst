-- Semantic memory (RAG): pgvector-backed store of everything the product has
-- told this user — digests, persisted news items, chat answers — so the chat
-- agent can answer "what did you tell me about NVDA last month?" via the
-- recall_memory tool (app/tools/recall.py). Rows are a pure DERIVED CACHE of
-- digests/news_items/agent_runs: on an embedding-model change, truncate and
-- re-run scripts/backfill_memory.py — never data loss.
--
-- Supabase note: extensions install into the "extensions" schema there. If
-- the restricted runtime role's search_path doesn't resolve the vector type,
-- run: ALTER ROLE <runtime_role> SET search_path = public, extensions;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memory_chunks (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001'
                    REFERENCES users(id),
  source_type     text NOT NULL CHECK (source_type IN ('digest','news','chat','alert')),
  source_id       uuid NOT NULL,     -- digests.id / news_items.id / agent_runs.id / alerts.id
  chunk_index     int  NOT NULL DEFAULT 0,
  content         text NOT NULL,     -- the exact text that was embedded
  tickers         jsonb NOT NULL DEFAULT '[]'::jsonb,
  content_date    date NOT NULL,     -- the content's semantic date, not ingestion time
  embedding       vector(1024) NOT NULL,
  embedding_model text NOT NULL,
  created_at      timestamptz DEFAULT now(),
  UNIQUE (user_id, source_type, source_id, chunk_index)  -- idempotent re-ingest
);

-- HNSW over cosine distance: builds fine on an empty table (IVFFlat needs
-- representative data + list tuning) and recall is better at this scale.
CREATE INDEX IF NOT EXISTS idx_memory_chunks_embedding
  ON memory_chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_memory_chunks_user_date
  ON memory_chunks (user_id, content_date);

-- RLS: tenant isolation + owner-service-context escape (migration 012 pattern).
ALTER TABLE memory_chunks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS memory_chunks_tenant_isolation ON memory_chunks;
CREATE POLICY memory_chunks_tenant_isolation ON memory_chunks
  USING (
    user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
    OR NULLIF(current_setting('app.current_user_id', true), '')::uuid
       = '00000000-0000-0000-0000-000000000001'::uuid
  );
