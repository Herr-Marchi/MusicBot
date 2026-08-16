from __future__ import annotations

from music_bot.application.contracts.results.music import NowPlayingResult

from .base import PlaybackCommand


class NowPlayingCommand(PlaybackCommand[NowPlayingResult]):
    pass
