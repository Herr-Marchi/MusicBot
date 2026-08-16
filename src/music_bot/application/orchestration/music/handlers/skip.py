from __future__ import annotations

from music_bot.application.contracts.commands.music import SkipCommand
from music_bot.application.contracts.dto import TrackDto
from music_bot.application.contracts.results.music import SkipResult
from music_bot.application.mappers.music import map_track_to_dto
from music_bot.application.orchestration.music.handlers.base import HandlerOutcome
from music_bot.application.ports.music_player import GuildPlayer
from music_bot.domain.music.models import GuildPlayback


class SkipCommandHandler:
    def __init__(
        self,
        *,
        playback: GuildPlayback,
        player: GuildPlayer,
    ) -> None:
        self._playback: GuildPlayback = playback
        self._player: GuildPlayer = player

    async def handle(self, command: SkipCommand) -> HandlerOutcome[SkipResult]:
        await self._player.stop()
        has_tracks: bool = self._playback.skip()

        track: TrackDto | None = None
        if has_tracks:
            track = map_track_to_dto(self._playback.first_track)

        return HandlerOutcome(
            result=SkipResult(now_playing=track),
            mutated=True,
            interrupts_current_track=True,
            restart_playback=True,
        )
