from __future__ import annotations

import discord


class NotConnectedToVoiceError(Exception):
    def __init__(self) -> None:
        super().__init__("I'm not connected to a voice channel.")


class VoiceClientLookup:
    def __init__(self) -> None:
        self._client: discord.Client | None = None

    def bind(self, client: discord.Client) -> None:
        self._client = client

    def get(self, guild_id: int) -> discord.VoiceClient | None:
        if self._client is None:
            raise RuntimeError("VoiceClientLookup used before bind()")

        guild: discord.Guild | None = self._client.get_guild(guild_id)
        if guild is None:
            return None

        voice_client: discord.VoiceProtocol | None = guild.voice_client
        return voice_client if isinstance(voice_client, discord.VoiceClient) else None

    def require(self, guild_id: int) -> discord.VoiceClient:
        voice_client: discord.VoiceClient | None = self.get(guild_id)
        if voice_client is None:
            raise NotConnectedToVoiceError()

        return voice_client
