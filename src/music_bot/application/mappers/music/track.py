from __future__ import annotations

from music_bot.application.contracts.dto import QueuedTrackDto
from music_bot.domain.music.models import Track


def to_queued_track_dto(track: Track) -> QueuedTrackDto:
    return QueuedTrackDto(
        url=track.url,
        title=track.title,
        requested_by=track.requested_by,
        requested_at=track.requested_at,
        duration_seconds=track.duration_seconds,
    )
