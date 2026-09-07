from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str
    database_url_direct: str = ""

    # Gemini
    gemini_api_key: str
    # gemini-2.5-flash is retired for new API keys; gemini-3.6-flash is current but
    # capped at 20 requests/day on the free tier - gemini-3.5-flash-lite has proven to
    # have a separate, workable free-tier quota. Verified live 2026-09-06.
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_embedding_model: str = "models/gemini-embedding-001"
    embedding_dimensions: int = 768

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""

    # Decision engine
    confidence_threshold: float = 0.75
    high_value_threshold: float = 200.00

    # App
    log_level: str = "INFO"
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
