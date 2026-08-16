from __future__ import annotations

from music_bot.application.contracts.commands.music import StopCommand
from music_bot.application.contracts.results.music import StopResult
from music_bot.application.orchestration.music.handlers.base import HandlerOutcome
from music_bot.application.ports.music_player import GuildPlayer
from music_bot.domain.music.models import GuildPlayback


class StopCommandHandler:
    def __init__(self, *, playback: GuildPlayback, player: GuildPlayer) -> None:
        self._playback: GuildPlayback = playback
        self._player: GuildPlayer = player

    async def handle(self, command: StopCommand) -> HandlerOutcome[StopResult]:
        await self._player.stop()
        cleared: int = self._playback.clear()
        return HandlerOutcome(
            result=StopResult(cleared=cleared),
            mutated=True,
            interrupts_current_track=True,
            restart_playback=False,
        )
