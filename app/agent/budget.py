"""Budget accounting for an agent run: iterations, tokens, and USD cost.

A run stops gracefully when it would exceed either the iteration cap or the
cost cap. Cost is derived from per-model price constants in ``config.py`` — the
model name is passed in so pricing is never hardcoded at call sites.
"""

from __future__ import annotations

from app.config import ModelPrice, price_for


class Budget:
    def __init__(
        self,
        *,
        max_iterations: int,
        max_cost_usd: float,
        model: str,
    ) -> None:
        self.max_iterations = max_iterations
        self.max_cost_usd = max_cost_usd
        self._price: ModelPrice = price_for(model)

        self.iterations = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0

    def record_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Fold one model call's token usage into the running totals."""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost_usd += self._price.cost(input_tokens, output_tokens)

    def start_iteration(self) -> None:
        self.iterations += 1

    def iterations_exhausted(self) -> bool:
        return self.iterations >= self.max_iterations

    def cost_exceeded(self) -> bool:
        return self.cost_usd >= self.max_cost_usd

    def exceeded(self) -> bool:
        """True once either cap is hit — used to end a run after a turn."""
        return self.iterations_exhausted() or self.cost_exceeded()
