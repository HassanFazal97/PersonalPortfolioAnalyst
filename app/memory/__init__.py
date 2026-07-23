"""Semantic memory: Voyage embeddings + pgvector storage of what the product
has told each user (digests, news, chat answers), recalled at chat time by
the ``recall_memory`` tool. Fail-open by design — no VOYAGE_API_KEY, no-op."""
