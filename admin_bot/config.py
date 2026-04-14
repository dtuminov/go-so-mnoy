import os
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    admin_bot_token: str
    database_url: str
    admin_ids: list[int] = Field(
        description="Telegram user IDs разрешённых админов (через запятую в .env).",
    )
    main_bot_username: str | None = Field(
        default=None,
        description="Username основного (прод) бота для deep link шаблонов.",
    )

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> list[int]:
        if isinstance(value, list):
            return value
        if isinstance(value, int):
            return [value]
        if isinstance(value, str):
            return [int(x.strip()) for x in value.split(",") if x.strip()]
        return []


@lru_cache(maxsize=1)
def get_admin_settings() -> AdminSettings:
    return AdminSettings()
