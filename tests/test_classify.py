import json
import uuid
from types import SimpleNamespace

import app.tools.classify as classify
from app.agent.budget import Budget
from tests.fakes import FakeRepo, ScriptedAnthropic, text_turn


def _labels_turn(labels, **kw):
    return text_turn(json.dumps({"labels": labels}), **kw)


def _ctx(client, **kw):
    base = {"client": client, "repo": None, "run_id": None, "budget": None}
    base.update(kw)
    return SimpleNamespace(**base)


async def test_classify_news_attaches_risk_and_opportunity_signals():
    classify.cache_clear()
    client = ScriptedAnthropic(
        [
            _labels_turn(
                [
                    {"i": 0, "signal": "warning", "salience": 0.9, "rationale": "downgrade"},
                    {"i": 1, "signal": "opportunity", "salience": 0.7, "rationale": "beat"},
                ]
            )
        ]
    )
    items = [
        {"headline": "X cut to sell", "summary": "s"},
        {"headline": "Y beats estimates", "summary": "s"},
    ]
    out = await classify.classify_news(items, _ctx(client))
    assert out[0]["signal"] == "warning" and out[0]["salience"] == 0.9
    assert out[1]["signal"] == "opportunity" and out[1]["salience"] == 0.7


async def test_classify_news_is_noop_without_client():
    classify.cache_clear()
    out = await classify.classify_news([{"headline": "h", "summary": "s"}], None)
    assert "signal" not in out[0]


async def test_classify_news_caches_by_headline():
    classify.cache_clear()
    client = ScriptedAnthropic(
        [_labels_turn([{"i": 0, "signal": "warning", "salience": 0.5, "rationale": "r"}])]
    )
    ctx = _ctx(client)
    await classify.classify_news([{"headline": "Same headline", "summary": "s"}], ctx)
    # Whitespace-different but canonically identical -> served from cache, no 2nd call.
    out = await classify.classify_news([{"headline": "Same  headline", "summary": "s2"}], ctx)
    assert out[0]["signal"] == "warning"
    assert len(client.calls) == 1


async def test_classify_news_only_calls_model_for_uncached_items():
    classify.cache_clear()
    client = ScriptedAnthropic(
        [
            _labels_turn([{"i": 0, "signal": "warning", "salience": 0.5, "rationale": "r"}]),
            _labels_turn([{"i": 0, "signal": "opportunity", "salience": 0.6, "rationale": "r"}]),
        ]
    )
    ctx = _ctx(client)
    await classify.classify_news([{"headline": "A", "summary": "s"}], ctx)
    out = await classify.classify_news(
        [{"headline": "A", "summary": "s"}, {"headline": "B", "summary": "s"}], ctx
    )
    # Second batch only sent the uncached "B".
    second_payload = client.calls[1]["messages"][0]["content"]
    assert '"headline": "B"' in second_payload
    assert '"headline": "A"' not in second_payload
    assert out[0]["signal"] == "warning" and out[1]["signal"] == "opportunity"


async def test_classify_news_records_model_call_and_budget():
    classify.cache_clear()
    repo = FakeRepo()
    budget = Budget(max_iterations=5, max_cost_usd=1.0, model="claude-haiku-4-5")
    client = ScriptedAnthropic(
        [
            _labels_turn(
                [{"i": 0, "signal": "neutral", "salience": 0.1, "rationale": "r"}],
                in_tok=50,
                out_tok=10,
            )
        ]
    )
    ctx = _ctx(client, repo=repo, run_id=uuid.uuid4(), budget=budget)
    await classify.classify_news([{"headline": "h", "summary": "s"}], ctx)
    assert len(repo.model_calls) == 1
    assert budget.input_tokens == 50 and budget.output_tokens == 10
    assert budget.cost_usd > 0


async def test_classify_news_degrades_to_untagged_on_bad_json():
    classify.cache_clear()
    client = ScriptedAnthropic([text_turn("not json at all")])
    out = await classify.classify_news([{"headline": "h", "summary": "s"}], _ctx(client))
    # Malformed model output -> neutral fallback, never an exception.
    assert out[0]["signal"] == "neutral"
