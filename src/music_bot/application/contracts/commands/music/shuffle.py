from __future__ import annotations

from music_bot.application.contracts.results.music import ShuffleResult

from .base import PlaybackCommand


class ShuffleCommand(PlaybackCommand[ShuffleResult]):
    pass
