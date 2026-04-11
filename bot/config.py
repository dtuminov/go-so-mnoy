from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str
    database_url: str
    bot_username: str | None = Field(
        default=None,
        description="Username бота без @; для deep links из канала (пока опционально).",
    )

    @field_validator("bot_username", mode="before")
    @classmethod
    def normalize_bot_username(cls, value: object) -> str | None:
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            return None
        name = value.strip().lstrip("@")
        return name or None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
