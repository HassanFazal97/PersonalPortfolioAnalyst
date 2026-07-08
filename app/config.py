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
    "claude-haiku-4-5": ModelPrice(input_per_mtok=1.0, output_per_mtok=5.0),
}

# Fallback price for unknown models so cost accounting never crashes a run.
DEFAULT_MODEL_PRICE = ModelPrice(input_per_mtok=3.0, output_per_mtok=15.0)


def price_for(model: str) -> ModelPrice:
    return MODEL_PRICES.get(model, DEFAULT_MODEL_PRICE)


# The single owner's user id (user #1), seeded by migration 002. Until per-user
# auth (roadmap Phase 2), every request/run/write is attributed to this user.
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    finnhub_api_key: str = Field(default="", alias="FINNHUB_API_KEY")
    database_url: str = Field(default="", alias="DATABASE_URL")
    # Owner/privileged connection for running migrations (DDL). Falls back to
    # database_url. Set this when database_url is a restricted non-owner role.
    migration_database_url: str = Field(default="", alias="MIGRATION_DATABASE_URL")
    # Require TLS to the database (Supabase and most managed Postgres need this;
    # leave false for a local/Docker Postgres).
    db_ssl: bool = Field(default=False, alias="DB_SSL")
    # Service/owner token: internal callers (cron, Mac worker) and single-user
    # mode. Also grants owner access when Supabase Auth is not configured.
    api_token: str = Field(default="", alias="API_TOKEN")
    # Supabase Auth. Set SUPABASE_URL (https://<ref>.supabase.co) to verify the
    # project's asymmetric JWTs (ES256/RS256) via its JWKS endpoint — the current
    # default for new projects, and rotation-safe. SUPABASE_JWT_SECRET is the
    # legacy HS256 shared-secret fallback. Either (or both) enables per-user auth;
    # neither = single-user mode.
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_jwt_secret: str = Field(default="", alias="SUPABASE_JWT_SECRET")
    supabase_jwt_aud: str = Field(default="authenticated", alias="SUPABASE_JWT_AUD")
    # Publishable (anon) key — public by design; embedded in the web app pages
    # so the browser can sign in with supabase-js.
    supabase_anon_key: str = Field(default="", alias="SUPABASE_ANON_KEY")
    # Service-role key (server-only, never sent to the browser). When set,
    # account deletion also removes the Supabase auth user via the admin API;
    # without it we delete app data only and the client signs out.
    supabase_service_role_key: str = Field(
        default="", alias="SUPABASE_SERVICE_ROLE_KEY"
    )

    model: str = Field(default="claude-sonnet-4-6", alias="MODEL")
    # Cheap, fast model for news signal tagging (risk/opportunity/neutral).
    classifier_model: str = Field(default="claude-haiku-4-5", alias="CLASSIFIER_MODEL")
    # Model for macro/geopolitical specialists (needs web_search support).
    macro_model: str = Field(default="claude-sonnet-4-6", alias="MACRO_MODEL")
    # How often the macro scan runs, in minutes. 0 disables the in-process
    # interval job (still triggerable via POST /macro/scan or external cron).
    macro_scan_interval_minutes: int = Field(default=0, alias="MACRO_SCAN_INTERVAL_MINUTES")
    macro_max_iterations: int = Field(default=30, alias="MACRO_MAX_ITERATIONS")
    macro_max_cost_usd: float = Field(default=2.00, alias="MACRO_MAX_COST_USD")
    # Owner attribution until per-user auth lands (roadmap Phase 2).
    default_user_id: str = Field(default=DEFAULT_USER_ID, alias="DEFAULT_USER_ID")

    chat_max_iterations: int = Field(default=10, alias="CHAT_MAX_ITERATIONS")
    chat_max_cost_usd: float = Field(default=0.50, alias="CHAT_MAX_COST_USD")
    digest_max_iterations: int = Field(default=25, alias="DIGEST_MAX_ITERATIONS")
    digest_max_cost_usd: float = Field(default=1.50, alias="DIGEST_MAX_COST_USD")

    max_tool_output_tokens: int = Field(default=6000, alias="MAX_TOOL_OUTPUT_TOKENS")
    tool_timeout_seconds: float = Field(default=10.0, alias="TOOL_TIMEOUT_SECONDS")

    # Plan gating + per-user monthly Anthropic cost caps (USD). Enforced against
    # agent_runs.cost_usd so a heavy user can't exceed their plan's economics.
    free_monthly_cost_cap_usd: float = Field(default=0.75, alias="FREE_MONTHLY_COST_CAP_USD")
    pro_monthly_cost_cap_usd: float = Field(default=6.00, alias="PRO_MONTHLY_COST_CAP_USD")
    free_daily_chat_limit: int = Field(default=5, alias="FREE_DAILY_CHAT_LIMIT")
    free_max_digest_holdings: int = Field(default=3, alias="FREE_MAX_DIGEST_HOLDINGS")

    digest_cron: str = Field(default="45 7 * * 1-5", alias="DIGEST_CRON")
    tz: str = Field(default="America/Toronto", alias="TZ")

    # ---- Multi-channel delivery (dispatcher + provider adapters) ----------
    # How often the dispatcher drains the outbound queue. 0 disables it.
    delivery_interval_seconds: int = Field(default=30, alias="DELIVERY_INTERVAL_SECONDS")
    delivery_max_attempts: int = Field(default=5, alias="DELIVERY_MAX_ATTEMPTS")
    # Public origin of this deployment (no trailing slash) — required for
    # validating Twilio webhook signatures, e.g. https://app.example.com
    public_base_url: str = Field(default="", alias="PUBLIC_BASE_URL")
    # Twilio SMS. All three must be set for the sms channel to exist.
    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    twilio_from_number: str = Field(default="", alias="TWILIO_FROM_NUMBER")
    # Resend email. Both must be set for the email channel to exist.
    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    email_from: str = Field(default="", alias="EMAIL_FROM")  # "Name <digest@domain>"

    # SnapTrade — Wealthsimple portfolio sync (https://snaptrade.com).
    snaptrade_client_id: str = Field(default="", alias="SNAPTRADE_CLIENT_ID")
    snaptrade_consumer_key: str = Field(default="", alias="SNAPTRADE_CONSUMER_KEY")
    snaptrade_user_id: str = Field(default="portfolio-owner", alias="SNAPTRADE_USER_ID")
    snaptrade_user_secret: str = Field(default="", alias="SNAPTRADE_USER_SECRET")
    # personal (dashboard SDK keys) | commercial (multi-user app keys) | auto
    snaptrade_auth_mode: str = Field(default="auto", alias="SNAPTRADE_AUTH_MODE")
    # Fernet key for encrypting per-user SnapTrade userSecret at rest.
    broker_secrets_key: str = Field(default="", alias="BROKER_SECRETS_KEY")


def monthly_cost_cap(plan: str, settings: Settings) -> float:
    """The per-user monthly USD cost ceiling for a plan."""
    return (
        settings.pro_monthly_cost_cap_usd
        if plan == "pro"
        else settings.free_monthly_cost_cap_usd
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
