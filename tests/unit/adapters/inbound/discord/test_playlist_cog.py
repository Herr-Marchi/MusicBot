from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from music_bot.adapters.inbound.discord.cogs.playlist.playlist import PlaylistCog
from music_bot.adapters.inbound.discord.dependencies import DiscordDependencies
from music_bot.adapters.inbound.discord.helpers import InteractionContext
from music_bot.adapters.inbound.discord.ui import Responder
from music_bot.adapters.inbound.discord.voice_manager import VoiceConnectionLease
from music_bot.application.contracts.errors import PlaylistNotFoundError
from music_bot.application.contracts.results.music import PlayPlaylistResult

type PlayCallback = Callable[[PlaylistCog, discord.Interaction, str], Awaitable[None]]


def _context() -> tuple[InteractionContext, AsyncMock, AsyncMock, AsyncMock]:
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    member = MagicMock(spec=discord.Member)
    member.id = 2
    responder = MagicMock(spec=Responder)
    info = AsyncMock()
    success = AsyncMock()
    announce = AsyncMock()
    responder.info = info
    responder.success = success
    responder.announce = announce
    return (
        InteractionContext(
            responder=responder,
            guild=guild,
            member=member,
        ),
        info,
        success,
        announce,
    )


def _connection() -> MagicMock:
    connection = MagicMock(spec=VoiceConnectionLease)
    connection.rollback = AsyncMock()
    voice_client = MagicMock(spec=discord.VoiceClient)
    voice_client.channel = MagicMock(spec=discord.VoiceChannel)
    connection.voice_client = voice_client
    return connection


def _cog(*, connection: MagicMock, playback_manager: MagicMock) -> PlaylistCog:
    voice_manager = MagicMock()
    voice_manager.connect = AsyncMock(return_value=connection)
    deps = DiscordDependencies(
        voice_manager=voice_manager,
        playback_manager=playback_manager,
        playlist_service=MagicMock(),
    )
    return PlaylistCog(MagicMock(spec=commands.Bot), deps)


async def _play(cog: PlaylistCog, *, playlist_id: str) -> None:
    callback = cast(PlayCallback, PlaylistCog.play.callback)
    await callback(
        cog,
        MagicMock(spec=discord.Interaction),
        playlist_id,
    )


@pytest.mark.unit
class TestPlaylistCogPlayConnectionLease:
    async def test_rolls_back_new_connection_for_empty_playlist(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        context, info, _, _ = _context()
        connection = _connection()
        playback_manager = MagicMock()
        playback_manager.execute = AsyncMock(
            return_value=PlayPlaylistResult(
                playlist_title="Empty",
                queued_count=0,
                started_playing=False,
            )
        )
        monkeypatch.setattr(
            "music_bot.adapters.inbound.discord.cogs.playlist.playlist.begin_interaction",
            AsyncMock(return_value=context),
        )

        await _play(
            _cog(connection=connection, playback_manager=playback_manager),
            playlist_id="playlist-1",
        )

        connection.rollback.assert_awaited_once_with()
        connection.retain.assert_not_called()
        info.assert_awaited_once_with("This playlist has no tracks.")

    async def test_rolls_back_new_connection_when_playlist_is_not_readable(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        context, _, _, _ = _context()
        connection = _connection()
        playback_manager = MagicMock()
        playback_manager.execute = AsyncMock(side_effect=PlaylistNotFoundError())
        monkeypatch.setattr(
            "music_bot.adapters.inbound.discord.cogs.playlist.playlist.begin_interaction",
            AsyncMock(return_value=context),
        )

        with pytest.raises(PlaylistNotFoundError):
            await _play(
                _cog(connection=connection, playback_manager=playback_manager),
                playlist_id="playlist-1",
            )

        connection.rollback.assert_awaited_once_with()
        connection.retain.assert_not_called()

    async def test_retains_connection_after_successful_queueing(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        context, _, success, announce = _context()
        connection = _connection()
        playback_manager = MagicMock()
        playback_manager.execute = AsyncMock(
            return_value=PlayPlaylistResult(
                playlist_title="Playlist",
                queued_count=2,
                started_playing=True,
            )
        )
        monkeypatch.setattr(
            "music_bot.adapters.inbound.discord.cogs.playlist.playlist.begin_interaction",
            AsyncMock(return_value=context),
        )

        await _play(
            _cog(connection=connection, playback_manager=playback_manager),
            playlist_id="playlist-1",
        )

        connection.retain.assert_called_once_with()
        connection.rollback.assert_not_awaited()
        success.assert_awaited_once()
        announce.assert_awaited_once()
