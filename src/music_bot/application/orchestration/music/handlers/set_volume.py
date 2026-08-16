from __future__ import annotations

from music_bot.application.contracts.commands.music import SetVolumeCommand
from music_bot.application.contracts.results.music import SetVolumeResult
from music_bot.application.orchestration.music.handlers.base import HandlerOutcome
from music_bot.application.ports.music_player import GuildPlayer
from music_bot.domain.music.models import GuildPlayback


class SetVolumeCommandHandler:
    def __init__(self, *, playback: GuildPlayback, player: GuildPlayer) -> None:
        self._playback: GuildPlayback = playback
        self._player: GuildPlayer = player

    async def handle(self, command: SetVolumeCommand) -> HandlerOutcome[SetVolumeResult]:
        await self._player.set_volume(command.volume)
        self._playback.set_volume(command.volume)

        return HandlerOutcome(
            result=SetVolumeResult(volume=self._playback.volume),
            mutated=True,
            interrupts_current_track=False,
            restart_playback=False,
        )
