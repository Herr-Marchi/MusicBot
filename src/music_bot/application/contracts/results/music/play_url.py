from __future__ import annotations

from dataclasses import dataclass

from music_bot.application.contracts.dto import TrackDto

from .base import PlaybackResult


@dataclass(frozen=True, slots=True)
class PlayUrlResult(PlaybackResult):
    track: TrackDto
    queue_size: int
