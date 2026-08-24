from __future__ import annotations

from dataclasses import dataclass

from music_bot.application.contracts.dto import QueuedTrackDto

from .base import PlaybackResult


@dataclass(frozen=True, slots=True)
class PlayUrlResult(PlaybackResult):
    track: QueuedTrackDto
    queue_size: int
