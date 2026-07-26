from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    telegram_bot_token: str = ""
    telegram_allowed_user_ids: Annotated[set[int], NoDecode] = Field(default_factory=set)
    shopify_store_domain: str = ""
    shopify_client_id: str = ""
    shopify_client_secret: str = ""
    shopify_admin_access_token: str = ""
    shopify_api_version: str = "2026-07"
    default_vendor: str = ""
    default_product_status: str = "DRAFT"
    default_currency: str = "UYU"
    exchange_rate_api_url: str = "https://open.er-api.com/v6/latest/{currency}"
    exchange_rate_cache_hours: int = 6
    default_markup_percent: float = 0
    max_images_per_product: int = 8
    request_timeout_seconds: int = 30
    database_url: str = "sqlite:///data/shopify_bot.db"
    log_level: str = "INFO"
    max_download_bytes: int = 15_000_000
    max_redirects: int = 5

    @field_validator("telegram_allowed_user_ids", mode="before")
    @classmethod
    def parse_ids(cls, value: object) -> set[int]:
        if isinstance(value, str):
            return {int(x.strip()) for x in value.split(",") if x.strip().isdigit()}
        return set(value or [])

    @field_validator("shopify_store_domain")
    @classmethod
    def valid_store(cls, value: str) -> str:
        value = value.strip().lower().removeprefix("https://").rstrip("/")
        if value and (not value.endswith(".myshopify.com") or "/" in value):
            raise ValueError("SHOPIFY_STORE_DOMAIN debe terminar en .myshopify.com")
        return value

    @property
    def configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_allowed_user_ids)

    @property
    def shopify_configured(self) -> bool:
        """Accept current Dev Dashboard credentials or a legacy Admin token."""
        return bool(
            self.shopify_store_domain
            and (
                self.shopify_admin_access_token
                or (self.shopify_client_id and self.shopify_client_secret)
            )
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
