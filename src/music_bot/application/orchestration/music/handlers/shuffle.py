from __future__ import annotations

from music_bot.application.contracts.commands.music import ShuffleCommand
from music_bot.application.contracts.results.music import ShuffleResult
from music_bot.application.orchestration.music.handlers.base import HandlerOutcome
from music_bot.application.ports.music_player import GuildPlayer
from music_bot.domain.music.models import GuildPlayback


class ShuffleCommandHandler:
    def __init__(
        self,
        *,
        playback: GuildPlayback,
        player: GuildPlayer,
    ) -> None:
        self._playback: GuildPlayback = playback
        self._player: GuildPlayer = player

    async def handle(self, command: ShuffleCommand) -> HandlerOutcome[ShuffleResult]:
        if self._playback.track_count < 2:
            return HandlerOutcome(
                result=ShuffleResult(shuffled=False, queue_size=self._playback.track_count),
                mutated=False,
                interrupts_current_track=False,
                restart_playback=False,
            )

        await self._player.stop()
        self._playback.shuffle()

        return HandlerOutcome(
            result=ShuffleResult(shuffled=True, queue_size=self._playback.track_count),
            mutated=True,
            interrupts_current_track=True,
            restart_playback=True,
        )
