"""Per-case fake tool layer: a dispatch dict injected into run_agent.

The model runs against recorded fixture outputs, so trajectories are
reproducible and free. A tool the case didn't script returns an is_error
"fixture miss" — the loop already handles is_error gracefully, and the report
flags the miss so an under-specified case isn't mistaken for a regression.
"""

from __future__ import annotations

from typing import Any

from app.tools.registry import CHAT_TOOLS


def build_fake_dispatch(
    fixtures: dict[str, dict[str, Any]], miss_log: list[str]
) -> dict[str, Any]:
    dispatch: dict[str, Any] = {}
    for schema in CHAT_TOOLS:
        name = schema["name"]
        spec = fixtures.get(name)

        def make(tool_name: str, tool_spec: dict[str, Any] | None):
            async def fake_tool(payload: dict[str, Any], ctx: Any) -> Any:
                if tool_spec is None:
                    miss_log.append(tool_name)
                    raise RuntimeError(
                        f"eval fixture miss: no recorded output for '{tool_name}'"
                    )
                if "error" in tool_spec:
                    raise RuntimeError(str(tool_spec["error"]))
                return tool_spec["default"]

            return fake_tool

        dispatch[name] = make(name, spec)
    return dispatch
