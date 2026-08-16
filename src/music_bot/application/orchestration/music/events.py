from __future__ import annotations

from dataclasses import dataclass

from music_bot.application.ports.music_player import TrackFinishedCallback
from music_bot.domain.music.models import Track


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackFinishedEvent:
    track: Track
    callback: TrackFinishedCallback
    exception: Exception | None
