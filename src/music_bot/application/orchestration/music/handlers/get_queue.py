from __future__ import annotations

from music_bot.application.contracts.commands.music import GetQueueCommand
from music_bot.application.contracts.results.music import GetQueueResult
from music_bot.application.mappers.music import to_queued_track_dto
from music_bot.application.orchestration.music.handlers.base import HandlerOutcome
from music_bot.domain.music.models import GuildPlayback


class GetQueueCommandHandler:
    def __init__(self, *, playback: GuildPlayback) -> None:
        self._playback: GuildPlayback = playback

    async def handle(self, command: GetQueueCommand) -> HandlerOutcome[GetQueueResult]:
        return HandlerOutcome(
            result=GetQueueResult(
                tracks=tuple(to_queued_track_dto(track) for track in self._playback.tracks)
            ),
            mutated=False,
            interrupts_current_track=False,
            restart_playback=False,
        )
