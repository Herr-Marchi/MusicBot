from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from music_bot.adapters.inbound.discord.cogs.playback.playback import PlaybackCog
from music_bot.adapters.inbound.discord.dependencies import DiscordDependencies
from music_bot.adapters.inbound.discord.helpers import InteractionContext
from music_bot.adapters.inbound.discord.ui import Responder
from music_bot.adapters.inbound.discord.voice_manager import VoiceConnectionLease
from music_bot.application.contracts.dto import QueuedTrackDto
from music_bot.application.contracts.results.music import PlayUrlResult
from music_bot.application.ports.track_source import TrackSourceError

type PlayCallback = Callable[[PlaybackCog, discord.Interaction, str], Awaitable[None]]


def _context() -> tuple[InteractionContext, AsyncMock]:
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    member = MagicMock(spec=discord.Member)
    member.id = 2
    responder = MagicMock(spec=Responder)
    success = AsyncMock()
    responder.success = success
    responder.announce = AsyncMock()
    return (
        InteractionContext(
            responder=responder,
            guild=guild,
            member=member,
        ),
        success,
    )


def _connection() -> tuple[VoiceConnectionLease, AsyncMock]:
    voice_client = MagicMock(spec=discord.VoiceClient)
    voice_client.channel = MagicMock(spec=discord.VoiceChannel)
    disconnect = AsyncMock()
    voice_client.disconnect = disconnect
    return VoiceConnectionLease(voice_client=voice_client, created=True), disconnect


def _cog(*, connection: VoiceConnectionLease, playback_manager: MagicMock) -> PlaybackCog:
    voice_manager = MagicMock()
    voice_manager.connect = AsyncMock(return_value=connection)
    deps = DiscordDependencies(
        voice_manager=voice_manager,
        playback_manager=playback_manager,
        playlist_service=MagicMock(),
    )
    return PlaybackCog(MagicMock(spec=commands.Bot), deps)


async def _play(cog: PlaybackCog) -> None:
    callback = cast(PlayCallback, PlaybackCog.play.callback)
    await callback(
        cog,
        MagicMock(spec=discord.Interaction),
        "https://example.com/track",
    )


@pytest.mark.unit
class TestPlaybackCogPlayConnectionLease:
    async def test_rolls_back_new_connection_when_resolution_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        context, _ = _context()
        connection, disconnect = _connection()
        playback_manager = MagicMock()
        playback_manager.execute = AsyncMock(side_effect=TrackSourceError("broken"))
        monkeypatch.setattr(
            "music_bot.adapters.inbound.discord.cogs.playback.playback.begin_interaction",
            AsyncMock(return_value=context),
        )

        with pytest.raises(TrackSourceError, match="broken"):
            await _play(_cog(connection=connection, playback_manager=playback_manager))

        disconnect.assert_awaited_once_with(force=False)

    async def test_retains_new_connection_after_successful_queueing(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        context, success = _context()
        connection, disconnect = _connection()
        playback_manager = MagicMock()
        playback_manager.execute = AsyncMock(
            return_value=PlayUrlResult(
                track=QueuedTrackDto(
                    url="https://example.com/track",
                    title="Track",
                    requested_by=2,
                    requested_at=datetime.now(UTC),
                    duration_seconds=1,
                ),
                queue_size=1,
            )
        )
        monkeypatch.setattr(
            "music_bot.adapters.inbound.discord.cogs.playback.playback.begin_interaction",
            AsyncMock(return_value=context),
        )

        await _play(_cog(connection=connection, playback_manager=playback_manager))

        disconnect.assert_not_awaited()
        success.assert_awaited_once()
