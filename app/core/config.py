from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_base_url: str | None = None
    log_level: str = "INFO"

    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
    telegram_enabled: bool = False
    telegram_polling_enabled: bool = False
    telegram_webhook_path: str = "/api/telegram/webhook"

    openai_api_key: str | None = None
    openai_model_main: str = "gpt-4o"
    openai_model_fast: str = "gpt-4o-mini"
    openai_model_embedding: str = "text-embedding-3-small"
    openai_max_retries: int = 3
    openai_timeout_sec: int = 30

    supabase_url: str | None = None
    supabase_service_key: str | None = None
    supabase_db_url: str | None = None

    bitrix_webhook_url: str | None = None
    bitrix_default_manager_id: int | None = None
    bitrix_deal_category_id: int = 0
    bitrix_high_urgency_user_ids: str = ""
    bitrix_incoming_webhook_secret: str | None = None

    agency_city: str = "Новосибирск"
    agency_name: str = "Новактив"
    agency_phone: str | None = None
    agency_timezone: str = "Asia/Novosibirsk"
    property_site_base_url: str = "https://novactiv.ru/property"
    quickdeal_feed_url: str | None = None
    quickdeal_sync_batch_size: int = 100
    quickdeal_sync_interval_minutes: int = 60
    agency_work_hours_start: str = "09:00"
    agency_work_hours_end: str = "21:00"
    premium_budget_threshold_rub: int = 20_000_000
    mortgage_partners: str = Field(default="", description="Comma-separated bank partner names")

    rate_limit_messages_per_minute: int = 10
    rate_limit_messages_per_hour: int = 100
    max_context_messages: int = 15
    summary_every_n_messages: int = 10
    max_tool_iterations: int = 5

    admin_username: str = "admin"
    admin_password: str | None = None
    openai_main_input_usd_per_1m: float = 2.50
    openai_main_output_usd_per_1m: float = 10.00
    openai_fast_input_usd_per_1m: float = 0.15
    openai_fast_output_usd_per_1m: float = 0.60

    followup_step_1_hours: int = 24
    followup_step_2_days: int = 3
    followup_step_3_days: int = 7

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
