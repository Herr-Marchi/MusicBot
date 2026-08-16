from __future__ import annotations

import discord

from music_bot.adapters.discord import VoiceClientLookup
from music_bot.adapters.inbound.discord.errors import (
    NotInSameVoiceChannelError,
    NotInVoiceError,
    UnsupportedVoiceChannelError,
    VoiceConnectionError,
    VoiceForbiddenError,
    VoiceTimeoutError,
)


class DiscordVoiceManager:
    def __init__(self, *, lookup: VoiceClientLookup) -> None:
        self._lookup: VoiceClientLookup = lookup

    async def connect(
        self,
        *,
        guild: discord.Guild,
        member: discord.Member,
    ) -> discord.VoiceClient:
        voice_state: discord.VoiceState | None = member.voice
        if voice_state is None or voice_state.channel is None:
            raise NotInVoiceError()

        connectable: discord.abc.Connectable = voice_state.channel
        if not isinstance(connectable, discord.VoiceChannel):
            raise UnsupportedVoiceChannelError()

        voice_channel: discord.VoiceChannel = connectable
        voice_protocol: discord.VoiceProtocol | None = guild.voice_client

        try:
            if isinstance(voice_protocol, discord.VoiceClient):
                voice_client: discord.VoiceClient = voice_protocol
                if voice_client.channel != voice_channel:
                    # Moving the bot is controlling playback for everyone
                    # already listening only someone in its current
                    # channel may do that
                    raise NotInSameVoiceChannelError()
            else:
                voice_client = await voice_channel.connect()
        except TimeoutError as exc:
            raise VoiceTimeoutError() from exc
        except discord.Forbidden as exc:
            raise VoiceForbiddenError() from exc
        except (discord.ClientException, discord.HTTPException) as exc:
            raise VoiceConnectionError() from exc

        return voice_client

    async def disconnect(self, *, guild_id: int) -> None:
        voice_client: discord.VoiceClient = self._lookup.require(guild_id)

        try:
            await voice_client.disconnect(force=False)
        except TimeoutError as exc:
            raise VoiceTimeoutError() from exc
        except (discord.ClientException, discord.HTTPException) as exc:
            raise VoiceConnectionError() from exc

    def require_voice_client(self, guild_id: int) -> discord.VoiceClient:
        return self._lookup.require(guild_id)

    def require_same_channel(
        self,
        *,
        guild_id: int,
        member: discord.Member,
    ) -> discord.VoiceClient:
        voice_client: discord.VoiceClient = self._lookup.require(guild_id)
        voice_state: discord.VoiceState | None = member.voice
        member_channel: discord.abc.Connectable | None = (
            voice_state.channel if voice_state is not None else None
        )
        if member_channel != voice_client.channel:
            raise NotInSameVoiceChannelError()

        return voice_client
