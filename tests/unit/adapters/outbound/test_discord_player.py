from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import cast
from unittest.mock import MagicMock

import pytest

from music_bot.adapters.discord import VoiceClientLookup
from music_bot.adapters.outbound.discord_player import player as player_module
from music_bot.adapters.outbound.discord_player.player import DiscordGuildPlayer
from music_bot.application.ports.music_player import PlaybackSettings
from music_bot.application.ports.track_source import TrackMetadata, TrackSource


class StreamResolver(TrackSource):
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error: Exception | None = error

    async def validate_url(self, *, source_url: str) -> TrackSource:
        return self

    async def _resolve_metadata(self, *, source_url: str) -> TrackMetadata:
        raise AssertionError("metadata resolution is not expected")

    async def _resolve_stream(self, *, source_url: str) -> str:
        if self._error is not None:
            raise self._error
        return f"{source_url}#stream"


class HangingStreamResolver(TrackSource):
    def __init__(self) -> None:
        self.started: asyncio.Event = asyncio.Event()
        self.cancelled: bool = False

    async def validate_url(self, *, source_url: str) -> TrackSource:
        return self

    async def _resolve_metadata(self, *, source_url: str) -> TrackMetadata:
        raise AssertionError("metadata resolution is not expected")

    async def _resolve_stream(self, *, source_url: str) -> str:
        self.started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("unreachable")


class VoiceLookup:
    def __init__(self, voice_client: MagicMock) -> None:
        self._voice_client: MagicMock = voice_client

    def require(self, guild_id: int) -> MagicMock:
        return self._voice_client

    def get(self, guild_id: int) -> MagicMock:
        return self._voice_client


@pytest.fixture
def voice_client() -> MagicMock:
    voice = MagicMock()
    voice.is_playing.return_value = False
    voice.is_paused.return_value = False
    return voice


def settings() -> PlaybackSettings:
    return PlaybackSettings(volume=40, is_paused=False)


@pytest.mark.unit
class TestDiscordGuildPlayer:
    async def test_play_starts_in_background(
        self,
        voice_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        audio = MagicMock()
        source = MagicMock()
        ffmpeg_audio = MagicMock(return_value=audio)
        volume_transformer = MagicMock(return_value=source)
        monkeypatch.setattr(player_module.discord, "FFmpegPCMAudio", ffmpeg_audio)
        monkeypatch.setattr(
            player_module.discord,
            "PCMVolumeTransformer",
            volume_transformer,
        )
        player = DiscordGuildPlayer(
            guild_id=1,
            voice_client_lookup=cast(VoiceClientLookup, VoiceLookup(voice_client)),
            stream_resolver=StreamResolver(),
        )
        finished: Callable[[Exception | None], None] = MagicMock()

        await player.play(
            url="https://example.com/track",
            settings=settings,
            on_finished=finished,
        )
        start_task: asyncio.Task[None] | None = player._start_task
        assert start_task is not None
        await start_task

        ffmpeg_audio.assert_called_once_with(
            source="https://example.com/track#stream",
            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            options="-vn",
        )
        volume_transformer.assert_called_once_with(audio, volume=0.4)
        voice_client.play.assert_called_once_with(source, after=finished)

    async def test_stream_failure_is_reported_through_finished_callback(
        self,
        voice_client: MagicMock,
    ) -> None:
        error = RuntimeError("stream failed")
        finished = MagicMock()
        player = DiscordGuildPlayer(
            guild_id=1,
            voice_client_lookup=cast(VoiceClientLookup, VoiceLookup(voice_client)),
            stream_resolver=StreamResolver(error=error),
        )

        await player.play(
            url="https://example.com/track",
            settings=settings,
            on_finished=finished,
        )
        start_task: asyncio.Task[None] | None = player._start_task
        assert start_task is not None
        await start_task

        finished.assert_called_once_with(error)
        voice_client.play.assert_not_called()

    async def test_stop_cancels_pending_stream_resolution(
        self,
        voice_client: MagicMock,
    ) -> None:
        resolver = HangingStreamResolver()
        player = DiscordGuildPlayer(
            guild_id=1,
            voice_client_lookup=cast(VoiceClientLookup, VoiceLookup(voice_client)),
            stream_resolver=resolver,
        )

        await player.play(
            url="https://example.com/track",
            settings=settings,
            on_finished=MagicMock(),
        )
        await asyncio.wait_for(resolver.started.wait(), timeout=1)

        await player.stop()

        assert resolver.cancelled is True
        assert player._start_task is None
        voice_client.play.assert_not_called()
        voice_client.stop.assert_called_once_with()
