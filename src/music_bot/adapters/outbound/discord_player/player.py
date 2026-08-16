from __future__ import annotations

import asyncio
from collections.abc import Callable

import discord

from music_bot.adapters.discord import VoiceClientLookup
from music_bot.application.ports.music_player import TrackFinishedCallback
from music_bot.application.ports.track_source import TrackStreamResolver


class DiscordGuildPlayer:
    def __init__(
        self,
        *,
        guild_id: int,
        voice_client_lookup: VoiceClientLookup,
        stream_resolver: TrackStreamResolver,
    ) -> None:
        self._guild_id: int = guild_id
        self._voice_client_lookup: VoiceClientLookup = voice_client_lookup
        self._stream_resolver: TrackStreamResolver = stream_resolver
        self._start_task: asyncio.Task[None] | None = None
        self._cancel_finished_callback: Callable[[], None] | None = None
        self._pause_requested: bool = False
        self._volume: int = 100

    async def play(
        self,
        *,
        url: str,
        volume: int,
        on_finished: TrackFinishedCallback,
    ) -> None:
        voice_client: discord.VoiceClient = self._voice_client_lookup.require(self._guild_id)
        if self._start_task is not None or voice_client.is_playing() or voice_client.is_paused():
            raise RuntimeError(f"Already playing in guild {self._guild_id}")

        self._pause_requested = False
        self._volume = volume
        is_callback_active: bool = True

        def cancel_callback() -> None:
            nonlocal is_callback_active
            is_callback_active = False

        def after(exception: Exception | None) -> None:
            nonlocal is_callback_active
            if not is_callback_active:
                return

            is_callback_active = False
            self._pause_requested = False
            if self._cancel_finished_callback is cancel_callback:
                self._cancel_finished_callback = None
            on_finished(exception)

        self._cancel_finished_callback = cancel_callback
        self._start_task = asyncio.create_task(
            self._start(
                voice_client=voice_client,
                url=url,
                after=after,
            )
        )

    async def stop(self) -> None:
        cancel_callback: Callable[[], None] | None = self._cancel_finished_callback
        if cancel_callback is not None:
            cancel_callback()
            self._cancel_finished_callback = None

        self._pause_requested = False

        start_task: asyncio.Task[None] | None = self._start_task
        if start_task is not None:
            start_task.cancel()
            try:
                await start_task
            except asyncio.CancelledError:
                pass
            finally:
                if self._start_task is start_task:
                    self._start_task = None

        voice_client: discord.VoiceClient | None = self._voice_client_lookup.get(self._guild_id)
        if voice_client is not None:
            voice_client.stop()

    async def pause(self) -> None:
        if self._start_task is not None:
            self._pause_requested = True
            return

        voice_client: discord.VoiceClient | None = self._voice_client_lookup.get(self._guild_id)
        if voice_client is not None and voice_client.is_playing():
            voice_client.pause()

    async def resume(self) -> None:
        if self._start_task is not None and self._pause_requested:
            self._pause_requested = False
            return

        voice_client: discord.VoiceClient | None = self._voice_client_lookup.get(self._guild_id)
        if voice_client is not None and voice_client.is_paused():
            voice_client.resume()

    async def set_volume(self, volume: int) -> None:
        self._volume = volume
        voice_client: discord.VoiceClient | None = self._voice_client_lookup.get(self._guild_id)
        if voice_client is None:
            return

        source: discord.AudioSource | None = voice_client.source
        if isinstance(source, discord.PCMVolumeTransformer):
            source.volume = volume / 100

    async def _start(
        self,
        *,
        voice_client: discord.VoiceClient,
        url: str,
        after: TrackFinishedCallback,
    ) -> None:
        source: discord.PCMVolumeTransformer[discord.FFmpegPCMAudio] | None = None
        source_started: bool = False
        try:
            stream_url: str = await self._stream_resolver.resolve_stream(source_url=url)
            audio: discord.FFmpegPCMAudio = discord.FFmpegPCMAudio(
                source=stream_url,
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn",
            )
            source = discord.PCMVolumeTransformer(audio, volume=self._volume / 100)
            voice_client.play(source, after=after)
            source_started = True
            if self._pause_requested:
                voice_client.pause()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            after(exc)
        finally:
            if source is not None and not source_started:
                source.cleanup()
            current_task: asyncio.Task[None] | None = asyncio.current_task()
            if self._start_task is current_task:
                self._start_task = None


class DiscordGuildPlayerFactory:
    def __init__(
        self,
        *,
        voice_client_lookup: VoiceClientLookup,
        stream_resolver: TrackStreamResolver,
    ) -> None:
        self._voice_client_lookup: VoiceClientLookup = voice_client_lookup
        self._stream_resolver: TrackStreamResolver = stream_resolver

    def __call__(self, guild_id: int) -> DiscordGuildPlayer:
        return DiscordGuildPlayer(
            guild_id=guild_id,
            voice_client_lookup=self._voice_client_lookup,
            stream_resolver=self._stream_resolver,
        )
