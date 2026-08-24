from __future__ import annotations

from music_bot.adapters.outbound.postgres.models import TrackModel
from music_bot.application.ports.track import StoredTrack


def to_stored_track(model: TrackModel) -> StoredTrack:
    return StoredTrack(
        id=str(model.id),
        url=model.url,
        title=model.title,
        duration_seconds=model.duration_seconds,
    )
