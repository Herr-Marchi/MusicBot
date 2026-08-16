from __future__ import annotations

from music_bot.application.contracts.commands.music import PauseCommand
from music_bot.application.contracts.results.music import PauseResult
from music_bot.application.orchestration.music.handlers.base import HandlerOutcome
from music_bot.application.ports.music_player import GuildPlayer
from music_bot.domain.music.models import GuildPlayback


class PauseCommandHandler:
    def __init__(self, *, playback: GuildPlayback, player: GuildPlayer) -> None:
        self._playback: GuildPlayback = playback
        self._player: GuildPlayer = player

    async def handle(self, command: PauseCommand) -> HandlerOutcome[PauseResult]:
        if self._playback.is_paused:
            return HandlerOutcome(
                result=PauseResult(paused=False),
                mutated=False,
                interrupts_current_track=False,
                restart_playback=False,
            )

        await self._player.pause()
        self._playback.pause()
        return HandlerOutcome(
            result=PauseResult(paused=True),
            mutated=True,
            interrupts_current_track=False,
            restart_playback=False,
        )
