from __future__ import annotations

from music_bot.application.contracts.commands.music import ResumeCommand
from music_bot.application.contracts.results.music import ResumeResult
from music_bot.application.orchestration.music.handlers.base import HandlerOutcome
from music_bot.application.ports.music_player import GuildPlayer
from music_bot.domain.music.models import GuildPlayback


class ResumeCommandHandler:
    def __init__(self, *, playback: GuildPlayback, player: GuildPlayer) -> None:
        self._playback: GuildPlayback = playback
        self._player: GuildPlayer = player

    async def handle(self, command: ResumeCommand) -> HandlerOutcome[ResumeResult]:
        if not self._playback.is_paused:
            return HandlerOutcome(
                result=ResumeResult(resumed=False),
                mutated=False,
                interrupts_current_track=False,
                restart_playback=False,
            )

        await self._player.resume()
        self._playback.resume()
        return HandlerOutcome(
            result=ResumeResult(resumed=True),
            mutated=True,
            interrupts_current_track=False,
            restart_playback=False,
        )
