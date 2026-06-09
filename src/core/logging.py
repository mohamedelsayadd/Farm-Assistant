import logging

from pydantic_settings import BaseSettings, SettingsConfigDict


class LoggingSettings(BaseSettings):
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file="src/.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def configure_logging() -> None:
    settings = LoggingSettings()
    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
