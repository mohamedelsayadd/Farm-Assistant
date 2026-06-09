import logging
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    DASHSCOPE_API_KEY: str = Field(...)
    DASHSCOPE_BASE_URL: str = Field(...)
    MODEL_NAME: str = Field(...)
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    CHAT_MEMORY_TTL_SECONDS: int = Field(default=3600, gt=0)
    CHAT_MEMORY_MAX_HISTORY_MESSAGES: int = Field(default=12, gt=0)

    model_config = SettingsConfigDict(
        env_file="src/.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    logger.info("settings_loaded env_file=src/.env dashscope_api_key_configured=%s", bool(settings.DASHSCOPE_API_KEY))
    return settings
