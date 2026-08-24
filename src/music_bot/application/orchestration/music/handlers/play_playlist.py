from __future__ import annotations

import logging

from music_bot.application.contracts.commands.music import (
    PlayPlaylistCommand,
    PlayUrlCommand,
)
from music_bot.application.contracts.results.music import (
    PlayPlaylistResult,
    PlayUrlResult,
)
from music_bot.application.orchestration.music.handlers.base import (
    CommandHandler,
    HandlerOutcome,
)
from music_bot.application.orchestration.playlists import PlaylistDetail, PlaylistService

logger: logging.Logger = logging.getLogger(__name__)


class PlayPlaylistCommandHandler:
    def __init__(
        self,
        *,
        playlist_service: PlaylistService,
        play_url_handler: CommandHandler[PlayUrlCommand, PlayUrlResult],
    ) -> None:
        self._playlist_service: PlaylistService = playlist_service
        self._play_url_handler: CommandHandler[PlayUrlCommand, PlayUrlResult] = play_url_handler

    async def handle(self, command: PlayPlaylistCommand) -> HandlerOutcome[PlayPlaylistResult]:
        logger.info(
            "Play playlist handler started guild_id=%s playlist_id=%s requested_by=%s",
            command.guild_id,
            command.playlist_id,
            command.requested_by,
        )
        detail: PlaylistDetail = await self._playlist_service.get(
            playlist_id=command.playlist_id,
            requested_by=command.requested_by,
        )
        queued_count: int = 0
        started_playing: bool = False

        for entry in detail.tracks:
            logger.debug(
                "Play playlist processing track guild_id=%s playlist_id=%s entry_id=%s "
                "position=%s track_id=%s",
                command.guild_id,
                command.playlist_id,
                entry.id,
                entry.position,
                entry.track.id,
            )
            outcome: HandlerOutcome[PlayUrlResult] = await self._play_url_handler.handle(
                PlayUrlCommand(
                    guild_id=command.guild_id,
                    requested_by=command.requested_by,
                    url=entry.track.url,
                )
            )
            if queued_count == 0:
                started_playing = outcome.result.queue_size == 1
            queued_count += 1

        logger.info(
            "Play playlist handler completed guild_id=%s playlist_id=%s queued_count=%s "
            "started_playing=%s",
            command.guild_id,
            command.playlist_id,
            queued_count,
            started_playing,
        )
        return HandlerOutcome(
            result=PlayPlaylistResult(
                playlist_title=detail.playlist.title,
                queued_count=queued_count,
                started_playing=started_playing,
            ),
            mutated=queued_count > 0,
            interrupts_current_track=False,
            restart_playback=False,
        )
