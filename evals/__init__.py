"""Eval harness: golden chat cases + labeled classifier headlines, replayed
through the REAL agent loop with FAKE tools and REAL model calls, scored by
deterministic checks plus an LLM judge, gated against a per-PROMPT_VERSION
baseline. Run: ``python -m evals.run --suite all``."""
