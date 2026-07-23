"""Golden-case and result models for the eval harness."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Rubric(BaseModel):
    # Deterministic checks, run in code (never delegated to the judge).
    must_mention: list[str] = Field(default_factory=list)
    must_not_mention: list[str] = Field(default_factory=list)
    # Semantic criteria, each judged as a binary pass/fail.
    criteria: list[dict[str, str]] = Field(default_factory=list)  # {id, text}


class GoldenCase(BaseModel):
    id: str
    question: str
    tags: list[str] = Field(default_factory=list)
    # Frozen user_context blob injected via compose_chat_system_prompt.
    context: dict[str, Any] = Field(default_factory=dict)
    # tool name -> {"default": <result>} (or {"error": "<msg>"} to force an
    # is_error tool_result).
    tool_fixtures: dict[str, dict[str, Any]] = Field(default_factory=dict)
    rubric: Rubric = Field(default_factory=Rubric)
    # Soft check: tools the trajectory is expected to include.
    expected_tools: list[str] = Field(default_factory=list)
    max_cost_usd: float = 0.25


class Verdict(BaseModel):
    criteria: list[dict[str, Any]] = Field(default_factory=list)
    hallucinations: list[str] = Field(default_factory=list)
    overall_pass: bool = False
    judge_error: bool = False
    raw: str = ""


class CaseResult(BaseModel):
    case_id: str
    answer: str = ""
    status: str = ""
    tools_used: list[str] = Field(default_factory=list)
    fixture_misses: list[str] = Field(default_factory=list)
    deterministic_failures: list[str] = Field(default_factory=list)
    expected_tools_missing: list[str] = Field(default_factory=list)
    verdict: Verdict | None = None
    cost_usd: float = 0.0
    error: str | None = None

    @property
    def passed(self) -> bool:
        if self.error or self.deterministic_failures:
            return False
        if self.verdict is None or self.verdict.judge_error:
            return False
        return self.verdict.overall_pass
