"""Deterministic price-anomaly alerts.

Statistical detectors (app/detectors/) decide what is anomalous over daily
log returns; the LLM only narrates the alert body afterward. Mirrors the
macro pipeline's cost structure: one global model-free scan, then a cheap
per-user Haiku call.
"""
