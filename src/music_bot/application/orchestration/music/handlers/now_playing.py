from __future__ import annotations

from music_bot.application.contracts.commands.music import NowPlayingCommand
from music_bot.application.contracts.results.music import NowPlayingResult
from music_bot.application.mappers.music import map_track_to_dto
from music_bot.application.orchestration.music.handlers.base import HandlerOutcome
from music_bot.domain.music.models import GuildPlayback


class NowPlayingCommandHandler:
    def __init__(self, *, playback: GuildPlayback) -> None:
        self._playback: GuildPlayback = playback

    async def handle(self, _command: NowPlayingCommand) -> HandlerOutcome[NowPlayingResult]:
        return HandlerOutcome(
            result=NowPlayingResult(
                track=map_track_to_dto(self._playback.first_track),
                is_paused=self._playback.is_paused,
            ),
            mutated=False,
            interrupts_current_track=False,
            restart_playback=False,
        )
