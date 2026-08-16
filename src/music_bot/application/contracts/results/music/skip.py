from __future__ import annotations

from dataclasses import dataclass

from music_bot.application.contracts.dto import TrackDto

from .base import PlaybackResult


@dataclass(frozen=True, slots=True)
class SkipResult(PlaybackResult):
    now_playing: TrackDto | None
