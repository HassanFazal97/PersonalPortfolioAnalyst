import app.agent.loop as loop
from app.agent.loop import _truncate, _validate_input, safe_dispatch
from app.tools.registry import GET_QUOTE_SCHEMA, ToolContext


def test_validate_input_missing_required():
    err = _validate_input(GET_QUOTE_SCHEMA["input_schema"], {})
    assert err and "tickers" in err


def test_validate_input_type_mismatch():
    err = _validate_input(GET_QUOTE_SCHEMA["input_schema"], {"tickers": "NVDA"})
    assert err and "array" in err


def test_validate_input_ok():
    assert _validate_input(GET_QUOTE_SCHEMA["input_schema"], {"tickers": ["NVDA"]}) is None


def test_truncate_adds_suffix():
    out = _truncate("x" * 100, 10)
    assert out.startswith("x" * 10)
    assert "[truncated 90 chars]" in out


def _ctx():
    from app.config import get_settings

    return ToolContext(settings=get_settings(), repo=None)


async def test_safe_dispatch_unknown_tool():
    result, err = await safe_dispatch(
        "nope", {}, ctx=_ctx(), schemas_by_name={}, timeout=5, max_output_tokens=6000
    )
    assert err is not None and "unknown tool" in result


async def test_safe_dispatch_validation_error_is_returned_not_raised():
    result, err = await safe_dispatch(
        "get_quote",
        {},
        ctx=_ctx(),
        schemas_by_name={"get_quote": GET_QUOTE_SCHEMA},
        timeout=5,
        max_output_tokens=6000,
    )
    assert err is not None and "tickers" in result


async def test_safe_dispatch_truncates_large_output(monkeypatch):
    async def huge(payload, ctx):
        return {"blob": "z" * 100_000}

    monkeypatch.setitem(loop.DISPATCH, "huge", huge)
    result, err = await safe_dispatch(
        "huge", {}, ctx=_ctx(), schemas_by_name={}, timeout=5, max_output_tokens=10
    )
    assert err is None
    assert "[truncated" in result
    assert len(result) < 100_000
