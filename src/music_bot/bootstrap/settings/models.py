from __future__ import annotations

from typing import ClassVar

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from music_bot.bootstrap.settings.types import LogLevel


class Settings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        extra="ignore", case_sensitive=True
    )

    discord_token: SecretStr = Field(alias="DISCORD_TOKEN")
    discord_guild_id: int | None = Field(default=None, alias="DISCORD_GUILD_ID")
    database_url: PostgresDsn = Field(alias="DATABASE_URL")
    redis_url: RedisDsn = Field(alias="REDIS_URL")
    redis_playback_ttl_seconds: int = Field(
        default=86_400,
        alias="REDIS_PLAYBACK_TTL_SECONDS",
        gt=0,
    )
    log_level: LogLevel = Field(default=LogLevel.DEBUG, alias="LOG_LEVEL")

    @field_validator("discord_token")
    @classmethod
    def validate_discord_token(cls, value: SecretStr) -> SecretStr:
        token: str = value.get_secret_value().strip()
        if not token:
            raise ValueError("Discord token cannot be empty")

        return value

    @field_validator("discord_guild_id", mode="before")
    @classmethod
    def validate_discord_guild_id(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None

        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_logging_level(cls, value: object) -> LogLevel:
        if isinstance(value, str):
            normalized: str = value.strip().upper()
            return LogLevel(normalized)
        if isinstance(value, LogLevel):
            return value

        raise TypeError(f"LOG_LEVEL must be a string, got {type(value).__name__}")
