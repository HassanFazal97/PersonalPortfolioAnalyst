from app.agent.budget import Budget


def _budget(**kw):
    return Budget(
        max_iterations=kw.get("max_iterations", 10),
        max_cost_usd=kw.get("max_cost_usd", 0.50),
        model="claude-sonnet-4-6",
    )


def test_record_usage_accumulates_tokens_and_cost():
    b = _budget()
    b.record_usage(1_000_000, 0)  # $3.00 input
    assert b.input_tokens == 1_000_000
    assert round(b.cost_usd, 4) == 3.0


def test_cost_exceeded():
    b = _budget(max_cost_usd=1.0)
    assert not b.cost_exceeded()
    b.record_usage(1_000_000, 0)  # $3 > $1
    assert b.cost_exceeded()
    assert b.exceeded()


def test_iterations_exhausted():
    b = _budget(max_iterations=2)
    b.start_iteration()
    assert not b.iterations_exhausted()
    b.start_iteration()
    assert b.iterations_exhausted()
    assert b.exceeded()
