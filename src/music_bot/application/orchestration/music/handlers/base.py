from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from music_bot.application.contracts.commands.music import PlaybackCommand
from music_bot.application.contracts.results.music import PlaybackResult


@dataclass(frozen=True, slots=True, kw_only=True)
class HandlerOutcome[ResultT: PlaybackResult]:
    result: ResultT
    mutated: bool
    interrupts_current_track: bool
    restart_playback: bool


class CommandHandler[
    CommandT: PlaybackCommand,
    ResultT: PlaybackResult,
](Protocol):
    async def handle(self, command: CommandT) -> HandlerOutcome[ResultT]: ...
