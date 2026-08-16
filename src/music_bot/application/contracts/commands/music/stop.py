from __future__ import annotations

from music_bot.application.contracts.results.music import StopResult

from .base import PlaybackCommand


class StopCommand(PlaybackCommand[StopResult]):
    pass
