from __future__ import annotations

import asyncio
import logging
from asyncio import Future
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import cast

from music_bot.application.contracts.commands.music import (
    PlaybackCommand,
    PlayPlaylistCommand,
    PlayUrlCommand,
)
from music_bot.application.contracts.results.music import PlaybackResult, PlayPlaylistResult
from music_bot.application.ports.music import GuildPlaybackRepository
from music_bot.application.ports.music_player import GuildPlayer, TrackFinishedCallback
from music_bot.application.ports.track_source import TrackMetadataResolver
from music_bot.domain.music.models import GuildPlayback, Track

from .command_handlers import PlaybackCommandDispatcher
from .event_listeners import TrackFinishedEventListener
from .events import TrackFinishedEvent
from .handlers import HandlerOutcome, PlayUrlCommandHandler, PlayUrlHandling

logger: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class CommandMessage:
    command: PlaybackCommand
    future: Future[PlaybackResult]


type ActorMessage = CommandMessage | TrackFinishedEvent


class GuildPlaybackActor:
    def __init__(
        self,
        *,
        guild_id: int,
        playback: GuildPlayback | None,
        playback_repository: GuildPlaybackRepository,
        player: GuildPlayer,
        metadata_resolver: TrackMetadataResolver,
        terminated_callback: Callable[[GuildPlaybackActor], None],
    ) -> None:
        self._guild_id: int = guild_id
        self._playback: GuildPlayback | None = playback
        self._playback_repository: GuildPlaybackRepository = playback_repository
        self._player: GuildPlayer = player
        self._terminated_callback: Callable[[GuildPlaybackActor], None] = terminated_callback
        self._play_url_handler: PlayUrlCommandHandler = PlayUrlCommandHandler(
            metadata_resolver=metadata_resolver
        )
        self._command_dispatcher: PlaybackCommandDispatcher | None = None
        self._track_finished_listener: TrackFinishedEventListener | None = None
        if playback is not None:
            self._activate(playback=playback)
        self._mailbox: asyncio.Queue[ActorMessage] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._finished_callback: TrackFinishedCallback | None = None

    @property
    def guild_id(self) -> int:
        return self._guild_id

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("GuildPlaybackActor is already running")

        self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        task: asyncio.Task[None] | None = self._task
        if task is None:
            return

        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

        if self._task is task:
            self._task = None
        self._reject_pending_messages(RuntimeError("GuildPlaybackActor stopped"))
        self._finished_callback = None
        await self._player.stop()

    async def execute[ResultT: PlaybackResult](self, command: PlaybackCommand[ResultT]) -> ResultT:
        self._ensure_running()
        if command.guild_id != self.guild_id:
            raise ValueError("Command guild does not match GuildPlaybackActor guild")

        future: asyncio.Future[PlaybackResult] = asyncio.get_running_loop().create_future()
        await self._mailbox.put(CommandMessage(command=command, future=future))
        return cast(ResultT, await future)

    def _ensure_running(self) -> None:
        if self._task is None:
            raise RuntimeError("GuildPlaybackActor is not running. Call start() first.")

    def _publish_track_finished(
        self,
        track: Track,
        callback: TrackFinishedCallback,
        exception: Exception | None,
    ) -> None:
        if self._task is not None:
            self._mailbox.put_nowait(
                TrackFinishedEvent(
                    track=track,
                    callback=callback,
                    exception=exception,
                )
            )

    async def _run(self) -> None:
        try:
            while True:
                message: ActorMessage = await self._mailbox.get()
                try:
                    match message:
                        case CommandMessage() as command_message:
                            await self._execute_command(command_message)
                        case TrackFinishedEvent() as event:
                            await self._track_finished(event)
                except asyncio.CancelledError:
                    if isinstance(message, CommandMessage) and not message.future.done():
                        message.future.set_exception(RuntimeError("GuildPlaybackActor stopped"))
                    raise
                except Exception as exc:
                    if isinstance(message, CommandMessage):
                        if not message.future.done():
                            message.future.set_exception(exc)
                    else:
                        logger.exception(
                            "Unhandled exception in guild %s playback actor",
                            self.guild_id,
                        )
                finally:
                    self._mailbox.task_done()

                if self._playback is None or self._playback.track_count == 0:
                    self._reject_pending_messages(RuntimeError("GuildPlaybackActor playback ended"))
                    self._terminated_callback(self)
                    return
        finally:
            self._task = None

    async def _execute_command(self, message: CommandMessage) -> None:
        result: PlaybackResult
        match message.command:
            case PlayUrlCommand():
                result = await self._play_url(message.command)
            case PlayPlaylistCommand():
                result = await self._play_playlist(message.command)
            case _:
                playback, command_dispatcher = self._require_playback()
                outcome: HandlerOutcome[PlaybackResult] = await command_dispatcher.handle(
                    message.command
                )

                if outcome.interrupts_current_track:
                    self._finished_callback = None

                if outcome.mutated:
                    try:
                        if outcome.restart_playback and playback.track_count > 0:
                            await self._start_playback_if_needed()
                    finally:
                        await self._persist()

                result = outcome.result

        if not message.future.done():
            message.future.set_result(result)

    async def _play_url(self, command: PlayUrlCommand) -> PlaybackResult:
        try:
            if self._playback is not None:
                await self._start_playback_if_needed()

            handling: PlayUrlHandling = await self._play_url_handler.handle(
                command,
                playback=self._playback,
            )
            if self._playback is None:
                self._activate(playback=handling.playback)

            await self._start_playback_if_needed()
            return handling.result
        finally:
            if self._playback is not None:
                await self._persist()

    async def _play_playlist(self, command: PlayPlaylistCommand) -> PlayPlaylistResult:
        # One mailbox message for the whole batch — not N separate
        # execute() calls from outside — so this is genuinely atomic with
        # respect to any other command for this guild (e.g. a concurrent
        # /skip can't land in the middle of it), and persists once at the
        # end instead of once per track.
        queued_count: int = 0
        started_playing: bool = False
        try:
            for url in command.urls:
                if self._playback is not None:
                    await self._start_playback_if_needed()

                handling: PlayUrlHandling = await self._play_url_handler.handle(
                    PlayUrlCommand(
                        guild_id=command.guild_id,
                        url=url,
                        requested_by=command.requested_by,
                    ),
                    playback=self._playback,
                )
                if self._playback is None:
                    self._activate(playback=handling.playback)

                await self._start_playback_if_needed()
                queued_count += 1
                started_playing = started_playing or handling.result.queue_size == 1
        finally:
            if self._playback is not None:
                await self._persist()

        return PlayPlaylistResult(queued_count=queued_count, started_playing=started_playing)

    async def _track_finished(self, event: TrackFinishedEvent) -> None:
        playback: GuildPlayback | None = self._playback
        if (
            event.callback is not self._finished_callback
            or playback is None
            or playback.track_count == 0
            or playback.first_track is not event.track
        ):
            return

        self._finished_callback = None
        listener: TrackFinishedEventListener | None = self._track_finished_listener
        if listener is None:
            raise RuntimeError("GuildPlaybackActor has no track-finished listener")

        try:
            has_tracks: bool = listener.handle(event)
            if has_tracks:
                await self._start_playback_if_needed()
        finally:
            await self._persist()

    async def _start_playback_if_needed(self) -> None:
        if self._finished_callback is not None:
            return

        playback, _ = self._require_playback()
        try:
            self._finished_callback = await self._start_playback(playback=playback)
            if playback.is_paused:
                await self._player.pause()
        except Exception:
            self._finished_callback = None
            playback.clear()
            await self._player.stop()
            raise

    async def _start_playback(self, *, playback: GuildPlayback) -> TrackFinishedCallback:
        track: Track = playback.first_track
        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()

        def on_finished(exception: Exception | None) -> None:
            loop.call_soon_threadsafe(
                self._publish_track_finished,
                track,
                on_finished,
                exception,
            )

        await self._player.play(
            url=track.url,
            volume=playback.volume,
            on_finished=on_finished,
        )
        return on_finished

    async def _persist(self) -> None:
        playback, _ = self._require_playback()
        if playback.track_count == 0:
            await self._playback_repository.delete(guild_id=self.guild_id)
        else:
            await self._playback_repository.save(playback=playback)

    def _require_playback(
        self,
    ) -> tuple[GuildPlayback, PlaybackCommandDispatcher]:
        if self._playback is None or self._command_dispatcher is None:
            raise RuntimeError("GuildPlaybackActor has not been activated")

        return self._playback, self._command_dispatcher

    def _create_command_dispatcher(
        self,
        *,
        playback: GuildPlayback,
    ) -> PlaybackCommandDispatcher:
        return PlaybackCommandDispatcher(
            playback=playback,
            player=self._player,
        )

    def _activate(self, *, playback: GuildPlayback) -> None:
        self._playback = playback
        self._command_dispatcher = self._create_command_dispatcher(playback=playback)
        self._track_finished_listener = TrackFinishedEventListener(playback=playback)

    def _reject_pending_messages(self, stop_exception: Exception) -> None:
        while True:
            try:
                message: ActorMessage = self._mailbox.get_nowait()
            except asyncio.QueueEmpty:
                break

            if isinstance(message, CommandMessage) and not message.future.done():
                message.future.set_exception(stop_exception)
            self._mailbox.task_done()
