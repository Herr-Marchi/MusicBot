from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from typing import Any

from music_bot.application.contracts.commands.music import (
    NowPlayingCommand,
    PlayUrlCommand,
    SkipCommand,
    StopCommand,
)
from music_bot.application.contracts.dto import TrackDto
from music_bot.application.contracts.results.music import (
    NowPlayingResult,
    PlayUrlResult,
    SkipResult,
    StopResult,
)
from music_bot.application.mappers.music import map_play_url_command_to_track, map_track_to_dto
from music_bot.application.orchestration.music.events import TrackFinishedEvent, TryStartEvent
from music_bot.application.orchestration.music.states import PlaybackState, StateContainer
from music_bot.application.ports import MusicPlayer, QueueRepository
from music_bot.domain.music.models import Queue, Track


class PlaybackService:
    def __init__(
        self,
        *,
        queue_repository: QueueRepository,
        music_player: MusicPlayer,
    ) -> None:
        self._queue_repository: QueueRepository = queue_repository
        self._music_player: MusicPlayer = music_player

        self._state: StateContainer = StateContainer()

    @property
    def state(self) -> StateContainer:
        return self._state

    def _transition_to(self, *, playback_state: PlaybackState, track: Track | None = None) -> None:
        self._state = self._state.copy_with(playback_state=playback_state, current_track=track)

    async def handle_play_url(
        self, command: PlayUrlCommand
    ) -> tuple[PlayUrlResult, Sequence[TryStartEvent]]:
        track: Track = map_play_url_command_to_track(command)
        guild_id: int = command.guild_id

        q: Queue = self._queue_repository.get_or_create(guild_id)
        q.enqueue(track)
        size_after: int = len(q)
        self._queue_repository.save(guild_id, q)

        result: PlayUrlResult = PlayUrlResult(queue_size=size_after, enqueued=True)
        return result, [TryStartEvent(guild_id=guild_id)]

    async def handle_stop(self, command: StopCommand) -> tuple[StopResult, Sequence[Any]]:
        guild_id: int = command.guild_id

        q: Queue | None = self._queue_repository.get(guild_id)
        queued: int = len(q) if q is not None else 0
        current: int = 1 if self._state.is_playing else 0
        cleared: int = queued + current
        self._queue_repository.delete(guild_id)

        await self._music_player.stop(context_id=guild_id)
        self._transition_to(playback_state=PlaybackState.IDLE, track=None)

        result: StopResult = StopResult(stopped=True, cleared=cleared)
        return result, []

    async def handle_skip(self, command: SkipCommand) -> tuple[SkipResult, Sequence[TryStartEvent]]:
        guild_id: int = command.guild_id

        if self._state.is_idle:
            return SkipResult(skipped=False, now_playing=None), []

        await self._music_player.stop(context_id=guild_id)
        self._transition_to(playback_state=PlaybackState.IDLE, track=None)

        result: SkipResult = SkipResult(skipped=True, now_playing=None)
        return result, [TryStartEvent(guild_id=guild_id)]

    async def handle_now_playing(
        self, command: NowPlayingCommand
    ) -> tuple[NowPlayingResult, Sequence[Any]]:
        track_dto: TrackDto | None = (
            map_track_to_dto(self._state.current_track) if self._state.current_track else None
        )

        result: NowPlayingResult = NowPlayingResult(
            is_playing=self._state.is_playing, track=track_dto
        )
        return result, []

    async def handle_try_start(
        self,
        *,
        guild_id: int,
        emit_finished_event: Callable[[TrackFinishedEvent], None],
    ) -> None:
        if self._state.is_playing:
            return

        q: Queue | None = self._queue_repository.get(guild_id)
        if q is None:
            return

        track: Track | None = q.dequeue()
        if track is None:
            return

        self._queue_repository.save(guild_id, q)
        self._transition_to(playback_state=PlaybackState.PLAYING, track=track)

        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()

        def _after(context_id: int, exc: Exception | None) -> None:
            loop.call_soon_threadsafe(
                emit_finished_event,
                TrackFinishedEvent(guild_id=context_id, exception=exc),
            )

        await self._music_player.play(context_id=guild_id, url=track.url, on_finished=_after)

    async def handle_track_finished(self, event: TrackFinishedEvent) -> Sequence[TryStartEvent]:
        self._transition_to(playback_state=PlaybackState.IDLE, track=None)

        return [TryStartEvent(guild_id=event.guild_id)]
