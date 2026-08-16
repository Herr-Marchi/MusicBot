from __future__ import annotations

from music_bot.application.contracts.results.music import PauseResult

from .base import PlaybackCommand


class PauseCommand(PlaybackCommand[PauseResult]):
    pass
