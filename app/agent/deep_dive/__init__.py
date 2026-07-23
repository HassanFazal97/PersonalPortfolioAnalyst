"""Portfolio Deep Dive: multi-agent research pipeline.

Stages: plan (one structured-JSON call) -> research (parallel specialist
run_agent sub-loops, each with its own toolset and budget) -> verify (an
adversarial critic re-checks load-bearing quantitative claims against tools)
-> synthesize (one structured-JSON call producing the final report).
"""

from app.agent.deep_dive.pipeline import run_deep_dive, run_deep_dives_for_all

__all__ = ["run_deep_dive", "run_deep_dives_for_all"]
