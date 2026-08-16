from __future__ import annotations

from music_bot.application.contracts.results.music import ResumeResult

from .base import PlaybackCommand


class ResumeCommand(PlaybackCommand[ResumeResult]):
    pass
