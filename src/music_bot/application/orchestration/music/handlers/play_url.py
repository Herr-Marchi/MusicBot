from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import ClassVar

from music_bot.application.contracts.commands.music import PlayUrlCommand
from music_bot.application.contracts.results.music import PlayUrlResult
from music_bot.application.mappers.music import to_queued_track_dto
from music_bot.application.orchestration.music.handlers.base import HandlerOutcome
from music_bot.application.orchestration.track_service import TrackService
from music_bot.application.ports.track import StoredTrack
from music_bot.application.ports.track_source import TrackSourceError
from music_bot.application.ports.uow import UoW, UoWFactory
from music_bot.domain.music.models import GuildPlayback, Track

type StartPlayback = Callable[[], Awaitable[None]]

logger: logging.Logger = logging.getLogger(__name__)


class PlayUrlCommandHandler:
    _RESOLVE_TIMEOUT_SECONDS: ClassVar[float] = 30.0

    def __init__(
        self,
        *,
        playback: GuildPlayback,
        track_service: TrackService,
        uow_factory: UoWFactory,
        start_playback: StartPlayback,
    ) -> None:
        self._playback: GuildPlayback = playback
        self._track_service: TrackService = track_service
        self._uow_factory: UoWFactory = uow_factory
        self._start_playback: StartPlayback = start_playback

    async def handle(self, command: PlayUrlCommand) -> HandlerOutcome[PlayUrlResult]:
        logger.debug(
            "Play URL handler started guild_id=%s requested_by=%s queue_size=%s",
            command.guild_id,
            command.requested_by,
            self._playback.track_count,
        )
        uow: UoW = self._uow_factory()
        async with uow:
            try:
                stored_track: StoredTrack = await asyncio.wait_for(
                    self._track_service.get_or_register(
                        url=command.url,
                        repository=uow.track_repository,
                    ),
                    timeout=self._RESOLVE_TIMEOUT_SECONDS,
                )
            except TimeoutError as exc:
                logger.warning(
                    "Play URL metadata resolution timed out guild_id=%s timeout_seconds=%.0f",
                    command.guild_id,
                    self._RESOLVE_TIMEOUT_SECONDS,
                )
                raise TrackSourceError(
                    f"Resolving the track timed out after {self._RESOLVE_TIMEOUT_SECONDS:.0f}s"
                ) from exc

            await uow.commit()

        track: Track = Track(
            url=stored_track.url,
            title=stored_track.title,
            requested_by=command.requested_by,
            duration_seconds=stored_track.duration_seconds,
        )
        self._playback.enqueue(track)
        logger.info(
            "Track enqueued guild_id=%s track_id=%s title=%r queue_size=%s requested_by=%s",
            command.guild_id,
            stored_track.id,
            track.title,
            self._playback.track_count,
            command.requested_by,
        )
        await self._start_playback()

        return HandlerOutcome(
            result=PlayUrlResult(
                track=to_queued_track_dto(track),
                queue_size=self._playback.track_count,
            ),
            mutated=True,
            interrupts_current_track=False,
            restart_playback=False,
        )
