from __future__ import annotations

from music_bot.application.contracts.results.music import SkipResult

from .base import PlaybackCommand


class SkipCommand(PlaybackCommand[SkipResult]):
    pass
