"""Portfolio-level quantitative risk engine.

Pure, I/O-free numerical code (mirrors ``app/detectors/`` in discipline): the
math lives here and is unit-tested against closed-form identities, while the
tools in ``app/tools/`` handle fetching, caching, and shaping results for the
model. Every number a user sees is computed here — the LLM only narrates.

Layers:
- ``returns`` — build a date-aligned, CAD-based daily log-returns matrix from
  adjusted closes (the load-bearing primitive everything else consumes).
- ``covariance`` — sample covariance + Ledoit-Wolf shrinkage.
- ``riskdecomp`` — portfolio volatility, diversification ratio, correlation
  structure, Euler/MCTR risk contributions, effective number of bets.
"""
