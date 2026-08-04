from __future__ import annotations

from dataclasses import dataclass

from music_bot.application.contracts.dto import TrackDto


@dataclass(frozen=True, slots=True)
class SkipResult:
    skipped: bool
    now_playing: TrackDto | None
