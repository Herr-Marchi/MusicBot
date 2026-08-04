from __future__ import annotations

from music_bot.application.contracts.dto import TrackDto
from music_bot.domain.music.models import Track


def map_track_to_dto(track: Track) -> TrackDto:
    return TrackDto(
        url=track.url,
        title=track.title,
        requested_by=track.requested_by,
        requested_at=track.requested_at,
        duration_seconds=track.duration_seconds,
    )
