from __future__ import annotations

from dataclasses import dataclass

from music_bot.application.contracts.dto import QueuedTrackDto

from .base import PlaybackResult


@dataclass(frozen=True, slots=True)
class GetQueueResult(PlaybackResult):
    tracks: tuple[QueuedTrackDto, ...]
