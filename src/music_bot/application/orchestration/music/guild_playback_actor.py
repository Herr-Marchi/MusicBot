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
)
from music_bot.application.contracts.results.music import PlaybackResult
from music_bot.application.orchestration.playlists import PlaylistService
from music_bot.application.orchestration.track_service import TrackService
from music_bot.application.ports.music import GuildPlaybackRepository
from music_bot.application.ports.music_player import (
    GuildPlayer,
    PlaybackSettings,
    TrackFinishedCallback,
)
from music_bot.application.ports.uow import UoWFactory
from music_bot.domain.music.models import GuildPlayback, Track

from .command_handlers import PlaybackCommandDispatcher
from .event_listeners import TrackFinishedEventListener
from .events import TrackFinishedEvent
from .handlers import HandlerOutcome

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
        playback: GuildPlayback,
        playback_repository: GuildPlaybackRepository,
        player: GuildPlayer,
        playlist_service: PlaylistService,
        track_service: TrackService,
        uow_factory: UoWFactory,
        terminated_callback: Callable[[GuildPlaybackActor], None],
    ) -> None:
        self._playback: GuildPlayback = playback
        self._playback_repository: GuildPlaybackRepository = playback_repository
        self._player: GuildPlayer = player
        self._terminated_callback: Callable[[GuildPlaybackActor], None] = terminated_callback
        self._command_dispatcher: PlaybackCommandDispatcher = PlaybackCommandDispatcher(
            playback=playback,
            player=player,
            playlist_service=playlist_service,
            track_service=track_service,
            uow_factory=uow_factory,
            start_playback=self._start_playback_if_needed,
        )
        self._track_finished_listener: TrackFinishedEventListener = TrackFinishedEventListener(
            playback=playback
        )
        self._mailbox: asyncio.Queue[ActorMessage] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._finished_callback: TrackFinishedCallback | None = None

    @property
    def guild_id(self) -> int:
        return self._playback.guild_id

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("GuildPlaybackActor is already running")

        logger.info(
            "Playback actor starting guild_id=%s queue_size=%s paused=%s",
            self.guild_id,
            self._playback.track_count,
            self._playback.is_paused,
        )
        self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        task: asyncio.Task[None] | None = self._task
        if task is None:
            logger.debug("Playback actor close skipped guild_id=%s state=stopped", self.guild_id)
            return

        logger.info("Playback actor closing guild_id=%s", self.guild_id)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

        if self._task is task:
            self._task = None
        self._reject_pending_messages(RuntimeError("GuildPlaybackActor stopped"))
        self._finished_callback = None
        await self._player.stop()
        logger.info("Playback actor closed guild_id=%s", self.guild_id)

    async def execute[ResultT: PlaybackResult](self, command: PlaybackCommand[ResultT]) -> ResultT:
        return await self.submit(command)

    def submit[ResultT: PlaybackResult](
        self,
        command: PlaybackCommand[ResultT],
    ) -> Future[ResultT]:
        self._ensure_running()
        if command.guild_id != self.guild_id:
            raise ValueError("Command guild does not match GuildPlaybackActor guild")

        future: asyncio.Future[PlaybackResult] = asyncio.get_running_loop().create_future()
        self._mailbox.put_nowait(CommandMessage(command=command, future=future))
        logger.debug(
            "Playback command queued guild_id=%s command=%s mailbox_size=%s",
            self.guild_id,
            type(command).__name__,
            self._mailbox.qsize(),
        )
        return cast(Future[ResultT], future)

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
            logger.debug(
                "Track finished callback published guild_id=%s title=%r has_error=%s",
                self.guild_id,
                track.title,
                exception is not None,
            )
            self._mailbox.put_nowait(
                TrackFinishedEvent(track=track, callback=callback, exception=exception)
            )

    async def _run(self) -> None:
        logger.debug("Playback actor mailbox loop started guild_id=%s", self.guild_id)
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
                        logger.warning(
                            "Playback command failed inside actor guild_id=%s command=%s "
                            "error_type=%s",
                            self.guild_id,
                            type(message.command).__name__,
                            type(exc).__name__,
                        )
                        if not message.future.done():
                            message.future.set_exception(exc)
                    else:
                        logger.exception("Unhandled playback event in guild %s", self.guild_id)
                finally:
                    self._mailbox.task_done()

                if self._playback.track_count == 0:
                    logger.info("Playback actor reached empty queue guild_id=%s", self.guild_id)
                    self._reject_pending_messages(RuntimeError("GuildPlaybackActor playback ended"))
                    self._terminated_callback(self)
                    return
        finally:
            self._task = None
            logger.debug("Playback actor mailbox loop stopped guild_id=%s", self.guild_id)

    async def _execute_command(self, message: CommandMessage) -> None:
        outcome: HandlerOutcome[PlaybackResult] | None = None
        command_name: str = type(message.command).__name__
        logger.debug(
            "Playback actor executing command guild_id=%s command=%s queue_size=%s",
            self.guild_id,
            command_name,
            self._playback.track_count,
        )
        try:
            outcome = await self._command_dispatcher.handle(message.command)
            if outcome.interrupts_current_track:
                self._finished_callback = None
            if outcome.restart_playback and self._playback.track_count > 0:
                await self._start_playback_if_needed()
        finally:
            if outcome is None or outcome.mutated:
                await self._persist()

        logger.debug(
            "Playback actor command completed guild_id=%s command=%s queue_size=%s "
            "paused=%s volume=%s loop=%s",
            self.guild_id,
            command_name,
            self._playback.track_count,
            self._playback.is_paused,
            self._playback.volume,
            self._playback.loop_current,
        )
        if not message.future.done():
            message.future.set_result(outcome.result)

    async def _track_finished(self, event: TrackFinishedEvent) -> None:
        if (
            event.callback is not self._finished_callback
            or self._playback.current_track is not event.track
        ):
            logger.debug(
                "Stale track finished event ignored guild_id=%s title=%r",
                self.guild_id,
                event.track.title,
            )
            return

        logger.info(
            "Track finished event handling guild_id=%s title=%r has_error=%s",
            self.guild_id,
            event.track.title,
            event.exception is not None,
        )
        self._finished_callback = None
        try:
            if self._track_finished_listener.handle(event):
                await self._start_playback_if_needed()
        finally:
            await self._persist()

    async def _start_playback_if_needed(self) -> None:
        if self._finished_callback is not None or self._playback.track_count == 0:
            logger.debug(
                "Playback start skipped guild_id=%s callback_active=%s queue_size=%s",
                self.guild_id,
                self._finished_callback is not None,
                self._playback.track_count,
            )
            return

        track: Track = self._playback.first_track
        logger.info(
            "Playback start requested guild_id=%s title=%r queue_size=%s paused=%s volume=%s",
            self.guild_id,
            track.title,
            self._playback.track_count,
            self._playback.is_paused,
            self._playback.volume,
        )
        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()

        def on_finished(exception: Exception | None) -> None:
            loop.call_soon_threadsafe(
                self._publish_track_finished,
                track,
                on_finished,
                exception,
            )

        def current_settings() -> PlaybackSettings:
            return PlaybackSettings(
                volume=self._playback.volume,
                is_paused=self._playback.is_paused,
            )

        try:
            await self._player.play(
                url=track.url,
                settings=current_settings,
                on_finished=on_finished,
            )
            self._finished_callback = on_finished
            logger.debug(
                "Playback start delegated to player guild_id=%s title=%r",
                self.guild_id,
                track.title,
            )
        except Exception:
            logger.exception(
                "Playback start delegation failed guild_id=%s title=%r",
                self.guild_id,
                track.title,
            )
            self._finished_callback = None
            self._playback.clear()
            await self._player.stop()
            raise

    async def _persist(self) -> None:
        if self._playback.track_count == 0:
            logger.debug("Deleting empty playback state guild_id=%s", self.guild_id)
            await self._playback_repository.delete(guild_id=self.guild_id)
        else:
            logger.debug(
                "Saving playback state guild_id=%s queue_size=%s paused=%s volume=%s loop=%s",
                self.guild_id,
                self._playback.track_count,
                self._playback.is_paused,
                self._playback.volume,
                self._playback.loop_current,
            )
            await self._playback_repository.save(playback=self._playback)

    def _reject_pending_messages(self, stop_exception: Exception) -> None:
        rejected_count: int = 0
        while True:
            try:
                message: ActorMessage = self._mailbox.get_nowait()
            except asyncio.QueueEmpty:
                break

            if isinstance(message, CommandMessage) and not message.future.done():
                message.future.set_exception(stop_exception)
                rejected_count += 1
            self._mailbox.task_done()
        if rejected_count:
            logger.info(
                "Pending playback commands rejected guild_id=%s count=%s reason=%s",
                self.guild_id,
                rejected_count,
                stop_exception,
            )
