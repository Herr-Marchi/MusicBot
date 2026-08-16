from __future__ import annotations

from music_bot.application.contracts.results.music import GetQueueResult

from .base import PlaybackCommand


class GetQueueCommand(PlaybackCommand[GetQueueResult]):
    pass
