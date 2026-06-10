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
    INPUT_GUARDRAIL_ENABLED: bool = Field(default=True)
    INPUT_GUARDRAIL_PROVIDER: str = Field(default="huggingface")
    INPUT_GUARDRAIL_MODEL_NAME: str = Field(default="NAMAA-Space/Ara-Prompt-Guard_V0")
    INPUT_GUARDRAIL_MAX_TOKENS: int = Field(default=512, gt=0)
    INPUT_GUARDRAIL_BLOCK_THRESHOLD: float = Field(default=0.5, ge=0.0, le=1.0)
    INPUT_GUARDRAIL_FAIL_CLOSED: bool = Field(default=True)
    INPUT_GUARDRAIL_BLOCK_MESSAGE: str = Field(
        default="لا أستطيع معالجة هذا الطلب لأنه قد يحتوي على تعليمات غير آمنة أو محاولة للتلاعب بالنظام."
    )

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
