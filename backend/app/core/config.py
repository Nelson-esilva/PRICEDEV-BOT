from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    database_url: str = "sqlite+aiosqlite:///./pricedev.db"
    log_level: str = "INFO"

    enable_scheduler: bool = True
    slo_seconds: int = 180

    enable_pelando: bool = False
    enable_shopee: bool = False
    enable_lomadee: bool = False
    enable_telegram_publish: bool = False

    pelando_poll_seconds: int = 15
    pelando_feed_pages: int = 4
    pelando_deal_details_per_poll: int = 20
    pelando_base_url: str = "https://api-web.pelando.com.br"
    pelando_user_agent: str = "PriceDevBot/0.1 (+local-dev)"

    shopee_poll_seconds: int = 120
    shopee_app_id: str = ""
    shopee_app_secret: str = ""
    shopee_keywords: str = "ssd,air fryer,monitor gamer,fone bluetooth,smartwatch"

    lomadee_app_token: str = ""
    lomadee_source_id: str = ""

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    min_historical_discount_pct: float = 20
    min_acceptance_score: int = 75
    anomaly_discount_pct: float = 50

    history_window_days: int = 90
    min_history_observations: int = 10
    min_history_distinct_days: int = 14

    allow_provisional_opportunities: bool = True
    allow_provisional_auto_publish: bool = False
    require_verified_price_for_historical_alert: bool = True

    score_weight_historical_discount: int = 30
    score_weight_history_quality: int = 20
    score_weight_identity: int = 15
    score_weight_price_verified: int = 15
    score_weight_freshness: int = 10
    score_weight_community: int = 10

    @property
    def shopee_keyword_list(self) -> list[str]:
        return [k.strip() for k in self.shopee_keywords.split(",") if k.strip()]

    @property
    def score_weights(self) -> dict[str, int]:
        return {
            "historical_discount": self.score_weight_historical_discount,
            "history_quality": self.score_weight_history_quality,
            "identity": self.score_weight_identity,
            "price_verified": self.score_weight_price_verified,
            "freshness": self.score_weight_freshness,
            "community": self.score_weight_community,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
