from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from music_bot.adapters.discord import VoiceClientLookup
from music_bot.adapters.inbound.discord.errors import NotInSameVoiceChannelError
from music_bot.adapters.inbound.discord.voice_manager import (
    DiscordVoiceManager,
    VoiceConnectionLease,
)


def _voice_client() -> MagicMock:
    voice_client = MagicMock(spec=discord.VoiceClient)
    voice_client.disconnect = AsyncMock()
    return voice_client


def _voice_member(channel: MagicMock) -> MagicMock:
    voice_state = MagicMock(spec=discord.VoiceState)
    voice_state.channel = channel
    member = MagicMock(spec=discord.Member)
    member.voice = voice_state
    return member


@pytest.mark.unit
class TestVoiceConnectionLease:
    async def test_rolls_back_only_new_connection(self) -> None:
        voice_client = _voice_client()
        connection = VoiceConnectionLease(
            voice_client=voice_client,
            created=True,
        )

        await connection.rollback()
        await connection.rollback()

        voice_client.disconnect.assert_awaited_once_with(force=False)


@pytest.mark.unit
class TestDiscordVoiceManagerConnect:
    async def test_new_connection_is_rollback_capable(self) -> None:
        voice_client = _voice_client()
        voice_channel = MagicMock(spec=discord.VoiceChannel)
        voice_channel.connect = AsyncMock(return_value=voice_client)
        guild = MagicMock(spec=discord.Guild)
        guild.voice_client = None
        manager = DiscordVoiceManager(lookup=MagicMock(spec=VoiceClientLookup))

        connection = await manager.connect(
            guild=guild,
            member=_voice_member(voice_channel),
        )
        await connection.rollback()

        voice_channel.connect.assert_awaited_once_with()
        voice_client.disconnect.assert_awaited_once_with(force=False)

    async def test_existing_connection_is_never_rolled_back(self) -> None:
        voice_client = _voice_client()
        voice_channel = MagicMock(spec=discord.VoiceChannel)
        voice_channel.connect = AsyncMock()
        voice_client.channel = voice_channel
        guild = MagicMock(spec=discord.Guild)
        guild.voice_client = voice_client
        manager = DiscordVoiceManager(lookup=MagicMock(spec=VoiceClientLookup))

        connection = await manager.connect(
            guild=guild,
            member=_voice_member(voice_channel),
        )
        await connection.rollback()

        voice_channel.connect.assert_not_awaited()
        voice_client.disconnect.assert_not_awaited()

    async def test_existing_connection_in_another_channel_is_rejected(self) -> None:
        voice_client = _voice_client()
        voice_client.channel = MagicMock(spec=discord.VoiceChannel)
        requested_channel = MagicMock(spec=discord.VoiceChannel)
        guild = MagicMock(spec=discord.Guild)
        guild.voice_client = voice_client
        manager = DiscordVoiceManager(lookup=MagicMock(spec=VoiceClientLookup))

        with pytest.raises(NotInSameVoiceChannelError):
            await manager.connect(
                guild=guild,
                member=_voice_member(requested_channel),
            )


@pytest.mark.unit
class TestVoiceConnectionLeaseRetention:
    async def test_does_not_disconnect_existing_connection(self) -> None:
        voice_client = _voice_client()
        connection = VoiceConnectionLease(
            voice_client=voice_client,
            created=False,
        )

        await connection.rollback()

        voice_client.disconnect.assert_not_awaited()

    async def test_retained_connection_is_not_rolled_back(self) -> None:
        voice_client = _voice_client()
        connection = VoiceConnectionLease(
            voice_client=voice_client,
            created=True,
        )
        connection.retain()

        await connection.rollback()

        voice_client.disconnect.assert_not_awaited()

    async def test_context_rolls_back_when_not_retained(self) -> None:
        voice_client = _voice_client()
        connection = VoiceConnectionLease(
            voice_client=voice_client,
            created=True,
        )

        async with connection:
            pass

        voice_client.disconnect.assert_awaited_once_with(force=False)
