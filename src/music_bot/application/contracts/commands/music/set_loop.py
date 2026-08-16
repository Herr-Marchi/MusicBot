from __future__ import annotations

from music_bot.application.contracts.results.music import SetLoopResult

from .base import PlaybackCommand


class SetLoopCommand(PlaybackCommand[SetLoopResult]):
    enabled: bool
