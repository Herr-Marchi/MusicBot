from __future__ import annotations

import pytest

from music_bot.bootstrap.settings.models import Settings

BASE_ENV: dict[str, str] = {
    "DISCORD_TOKEN": "token",
    "DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/db",
    "REDIS_URL": "redis://localhost:6379/0",
}


@pytest.mark.unit
class TestDiscordGuildId:
    def test_empty_string_is_treated_as_unset(self) -> None:
        settings: Settings = Settings.model_validate({**BASE_ENV, "DISCORD_GUILD_ID": ""})

        assert settings.discord_guild_id is None

    def test_missing_defaults_to_none(self) -> None:
        settings: Settings = Settings.model_validate(BASE_ENV)

        assert settings.discord_guild_id is None

    def test_valid_value_is_parsed(self) -> None:
        settings: Settings = Settings.model_validate({**BASE_ENV, "DISCORD_GUILD_ID": "123"})

        assert settings.discord_guild_id == 123
