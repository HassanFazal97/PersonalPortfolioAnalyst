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

    # ---- Price-anomaly detector scan (statistical, model-free) ------------
    # Cron for the daily scan (detector math is free; one Haiku call per user
    # with a flagged holding). "" disables the in-process job — still
    # triggerable via POST /anomaly/scan. Suggested: "30 16 * * 1-5" (after
    # the TSX/NYSE close, in TZ).
    anomaly_scan_cron: str = Field(default="", alias="ANOMALY_SCAN_CRON")
    # Calendar days of history fetched per ticker (~0.7x trading days).
    anomaly_history_days: int = Field(default=180, alias="ANOMALY_HISTORY_DAYS")
    # Detector thresholds operate on daily LOG RETURNS. Defaults chosen from
    # scripts/calibrate_detectors.py on 5y of real history (see README table):
    # zscore k=3 → ~3.9 FP/yr/ticker, 1-day spike lag; cusum h=8 → ~2.7
    # FP/yr/ticker, 11-day drift lag (h=6 doubled the FPs for no lag gain).
    # Re-run the calibration script before changing these.
    anomaly_zscore_window: int = Field(default=60, alias="ANOMALY_ZSCORE_WINDOW")
    anomaly_zscore_k: float = Field(default=3.0, alias="ANOMALY_ZSCORE_K")
    anomaly_cusum_warmup: int = Field(default=60, alias="ANOMALY_CUSUM_WARMUP")
    anomaly_cusum_delta: float = Field(default=0.5, alias="ANOMALY_CUSUM_DELTA")
    anomaly_cusum_h: float = Field(default=8.0, alias="ANOMALY_CUSUM_H")
    # Divergence (correlation break vs a benchmark) is off until a benchmark
    # ticker is set (e.g. XIU.TO or SPY); thresholds are the least
    # transferable from Shizen, so enable only after calibrating.
    anomaly_benchmark_ticker: str = Field(default="", alias="ANOMALY_BENCHMARK_TICKER")
    anomaly_divergence_window: int = Field(default=30, alias="ANOMALY_DIVERGENCE_WINDOW")
    anomaly_divergence_calibration: int = Field(
        default=120, alias="ANOMALY_DIVERGENCE_CALIBRATION"
    )
    anomaly_divergence_threshold: float = Field(
        default=3.5, alias="ANOMALY_DIVERGENCE_THRESHOLD"
    )
    # Flags below this severity are dropped before aggregation.
    anomaly_min_severity: float = Field(default=0.5, alias="ANOMALY_MIN_SEVERITY")
    # Days a ticker stays quiet after appearing in a price_anomaly alert.
    anomaly_cooldown_days: int = Field(default=3, alias="ANOMALY_COOLDOWN_DAYS")
    # Budget for the per-user narration call (Haiku).
    anomaly_max_cost_usd: float = Field(default=0.10, alias="ANOMALY_MAX_COST_USD")

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

    # ---- Scheduled-job health (job_heartbeats + /health staleness) --------
    # Interval jobs (delivery, macro) report degraded/offline after this many
    # missed intervals since the last success.
    job_degraded_factor: float = Field(default=3.0, alias="JOB_DEGRADED_FACTOR")
    job_offline_factor: float = Field(default=10.0, alias="JOB_OFFLINE_FACTOR")
    # A cron fire (digest, anomaly scan) only counts as missed once it is this
    # old; also passed to APScheduler so a fire up to this late still runs
    # instead of being silently skipped (the default grace is 1 second).
    digest_misfire_grace_seconds: int = Field(
        default=3600, alias="DIGEST_MISFIRE_GRACE_SECONDS"
    )

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
    # HMAC key for signed email unsubscribe links (CASL). Falls back to
    # API_TOKEN when unset; set a dedicated value so token rotation doesn't
    # break old unsubscribe links.
    unsubscribe_secret: str = Field(default="", alias="UNSUBSCRIBE_SECRET")
    # Discord OAuth2 app (scope webhook.incoming) — one-click "Connect
    # Discord". Both must be set for the connect flow to be offered; users
    # can always paste a webhook URL manually. Requires PUBLIC_BASE_URL so
    # the redirect URI matches what's registered in the Discord app.
    discord_client_id: str = Field(default="", alias="DISCORD_CLIENT_ID")
    discord_client_secret: str = Field(default="", alias="DISCORD_CLIENT_SECRET")

    # SnapTrade — brokerage portfolio sync (https://snaptrade.com).
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
