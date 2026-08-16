from __future__ import annotations

from music_bot.application.contracts.commands.music import SetLoopCommand
from music_bot.application.contracts.results.music import SetLoopResult
from music_bot.application.orchestration.music.handlers.base import HandlerOutcome
from music_bot.domain.music.models import GuildPlayback


class SetLoopCommandHandler:
    def __init__(self, *, playback: GuildPlayback) -> None:
        self._playback: GuildPlayback = playback

    async def handle(self, command: SetLoopCommand) -> HandlerOutcome[SetLoopResult]:
        if command.enabled:
            self._playback.enable_loop()
        else:
            self._playback.disable_loop()

        return HandlerOutcome(
            result=SetLoopResult(enabled=self._playback.loop_current),
            mutated=True,
            interrupts_current_track=False,
            restart_playback=False,
        )
