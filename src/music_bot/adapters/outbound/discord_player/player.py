from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlsplit

import discord

from music_bot.adapters.discord import VoiceClientLookup
from music_bot.application.ports.music_player import (
    PlaybackSettings,
    PlaybackSettingsProvider,
    TrackFinishedCallback,
)
from music_bot.application.ports.track_source import TrackStreamResolver

logger: logging.Logger = logging.getLogger(__name__)


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

    async def play(
        self,
        *,
        url: str,
        settings: PlaybackSettingsProvider,
        on_finished: TrackFinishedCallback,
    ) -> None:
        source_hostname: str | None = urlsplit(url).hostname
        logger.info(
            "Player play requested guild_id=%s source_hostname=%r",
            self._guild_id,
            source_hostname,
        )
        voice_client: discord.VoiceClient = self._voice_client_lookup.require(self._guild_id)
        start_pending: bool = self._start_task is not None
        is_playing: bool = voice_client.is_playing()
        is_paused: bool = voice_client.is_paused()
        if start_pending or is_playing or is_paused:
            logger.warning(
                "Player rejected duplicate play guild_id=%s start_pending=%s "
                "is_playing=%s is_paused=%s",
                self._guild_id,
                start_pending,
                is_playing,
                is_paused,
            )
            raise RuntimeError(f"Already playing in guild {self._guild_id}")

        self._start_task = asyncio.create_task(
            self._start(
                voice_client=voice_client,
                url=url,
                settings=settings,
                on_finished=on_finished,
            )
        )
        logger.debug("Player background start task created guild_id=%s", self._guild_id)

    async def stop(self) -> None:
        logger.info("Player stop requested guild_id=%s", self._guild_id)
        start_task: asyncio.Task[None] | None = self._start_task
        if start_task is not None:
            logger.debug("Cancelling pending player start guild_id=%s", self._guild_id)
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
            logger.info("Discord voice playback stopped guild_id=%s", self._guild_id)
        else:
            logger.debug("Player stop found no voice client guild_id=%s", self._guild_id)

    async def pause(self) -> None:
        logger.info("Player pause requested guild_id=%s", self._guild_id)
        voice_client: discord.VoiceClient | None = self._voice_client_lookup.get(self._guild_id)
        if voice_client is not None and voice_client.is_playing():
            voice_client.pause()
            logger.info("Discord voice playback paused guild_id=%s", self._guild_id)
        else:
            logger.debug("Player pause had no active playback guild_id=%s", self._guild_id)

    async def resume(self) -> None:
        logger.info("Player resume requested guild_id=%s", self._guild_id)
        voice_client: discord.VoiceClient | None = self._voice_client_lookup.get(self._guild_id)
        if voice_client is not None and voice_client.is_paused():
            voice_client.resume()
            logger.info("Discord voice playback resumed guild_id=%s", self._guild_id)
        else:
            logger.debug("Player resume found no paused playback guild_id=%s", self._guild_id)

    async def set_volume(self, volume: int) -> None:
        logger.info("Player volume requested guild_id=%s volume=%s", self._guild_id, volume)
        voice_client: discord.VoiceClient | None = self._voice_client_lookup.get(self._guild_id)
        if voice_client is None:
            logger.debug("Player volume found no voice client guild_id=%s", self._guild_id)
            return

        source: discord.AudioSource | None = voice_client.source
        if isinstance(source, discord.PCMVolumeTransformer):
            source.volume = volume / 100
            logger.info("Player volume applied guild_id=%s volume=%s", self._guild_id, volume)
        else:
            logger.debug(
                "Player volume found no adjustable source guild_id=%s source_type=%s",
                self._guild_id,
                type(source).__name__ if source is not None else None,
            )

    async def _start(
        self,
        *,
        voice_client: discord.VoiceClient,
        url: str,
        settings: PlaybackSettingsProvider,
        on_finished: TrackFinishedCallback,
    ) -> None:
        source: discord.PCMVolumeTransformer[discord.FFmpegPCMAudio] | None = None
        source_started: bool = False
        source_hostname: str | None = urlsplit(url).hostname
        try:
            logger.debug(
                "Player stream resolution started guild_id=%s source_hostname=%r",
                self._guild_id,
                source_hostname,
            )
            stream_url: str = await self._stream_resolver.resolve_stream(source_url=url)
            stream_hostname: str | None = urlsplit(stream_url).hostname
            logger.debug(
                "Player stream resolution completed guild_id=%s stream_hostname=%r",
                self._guild_id,
                stream_hostname,
            )
            current_settings: PlaybackSettings = settings()
            logger.debug(
                "Player settings read guild_id=%s volume=%s is_paused=%s",
                self._guild_id,
                current_settings.volume,
                current_settings.is_paused,
            )
            audio: discord.FFmpegPCMAudio = discord.FFmpegPCMAudio(
                source=stream_url,
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn",
            )
            source = discord.PCMVolumeTransformer(
                audio,
                volume=current_settings.volume / 100,
            )

            voice_client.play(source, after=on_finished)
            source_started = True
            logger.info(
                "Discord voice playback started guild_id=%s source_hostname=%r "
                "stream_hostname=%r volume=%s",
                self._guild_id,
                source_hostname,
                stream_hostname,
                current_settings.volume,
            )
            if current_settings.is_paused:
                voice_client.pause()
                logger.info("Discord voice playback started paused guild_id=%s", self._guild_id)
        except asyncio.CancelledError:
            logger.debug("Player start cancelled guild_id=%s", self._guild_id)
            raise
        except Exception as exc:
            logger.exception(
                "Player start failed guild_id=%s source_hostname=%r",
                self._guild_id,
                source_hostname,
            )
            on_finished(exc)
        finally:
            if source is not None and not source_started:
                source.cleanup()
            current_task: asyncio.Task[None] | None = asyncio.current_task()
            if self._start_task is current_task:
                self._start_task = None
            logger.debug(
                "Player start task finished guild_id=%s source_started=%s",
                self._guild_id,
                source_started,
            )


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
        logger.debug("Creating Discord guild player guild_id=%s", guild_id)
        return DiscordGuildPlayer(
            guild_id=guild_id,
            voice_client_lookup=self._voice_client_lookup,
            stream_resolver=self._stream_resolver,
        )
