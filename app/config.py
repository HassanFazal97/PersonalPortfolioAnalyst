"""Application configuration.

Single source of truth for API keys, model name, budgets, and price
constants. Loaded once via ``get_settings()`` (cached). Nothing else in the
codebase should read ``os.environ`` directly.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelPrice:
    """Per-million-token USD prices, used by ``budget.py`` for cost accounting."""

    def __init__(self, input_per_mtok: float, output_per_mtok: float) -> None:
        self.input_per_mtok = input_per_mtok
        self.output_per_mtok = output_per_mtok

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens / 1_000_000 * self.input_per_mtok
            + output_tokens / 1_000_000 * self.output_per_mtok
        )


# Price table keyed by model name. Update here, never at call sites.
MODEL_PRICES: dict[str, ModelPrice] = {
    "claude-sonnet-4-6": ModelPrice(input_per_mtok=3.0, output_per_mtok=15.0),
}

# Fallback price for unknown models so cost accounting never crashes a run.
DEFAULT_MODEL_PRICE = ModelPrice(input_per_mtok=3.0, output_per_mtok=15.0)


def price_for(model: str) -> ModelPrice:
    return MODEL_PRICES.get(model, DEFAULT_MODEL_PRICE)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    finnhub_api_key: str = Field(default="", alias="FINNHUB_API_KEY")
    database_url: str = Field(default="", alias="DATABASE_URL")
    # Require TLS to the database (Supabase and most managed Postgres need this;
    # leave false for a local/Docker Postgres).
    db_ssl: bool = Field(default=False, alias="DB_SSL")
    api_token: str = Field(default="", alias="API_TOKEN")

    model: str = Field(default="claude-sonnet-4-6", alias="MODEL")

    chat_max_iterations: int = Field(default=10, alias="CHAT_MAX_ITERATIONS")
    chat_max_cost_usd: float = Field(default=0.50, alias="CHAT_MAX_COST_USD")
    digest_max_iterations: int = Field(default=25, alias="DIGEST_MAX_ITERATIONS")
    digest_max_cost_usd: float = Field(default=1.50, alias="DIGEST_MAX_COST_USD")

    max_tool_output_tokens: int = Field(default=6000, alias="MAX_TOOL_OUTPUT_TOKENS")
    tool_timeout_seconds: float = Field(default=10.0, alias="TOOL_TIMEOUT_SECONDS")

    digest_cron: str = Field(default="45 7 * * 1-5", alias="DIGEST_CRON")
    tz: str = Field(default="America/Toronto", alias="TZ")

    # Phase B: the user's own number the Mac worker texts.
    imessage_recipient: str = Field(default="", alias="IMESSAGE_RECIPIENT")


@lru_cache
def get_settings() -> Settings:
    return Settings()
