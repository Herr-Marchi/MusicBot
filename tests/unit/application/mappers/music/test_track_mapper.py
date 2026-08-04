from __future__ import annotations

import pytest
from tests.typing_helper import MakeTrack

from music_bot.application.contracts.dto import TrackDto
from music_bot.application.mappers.music.track import map_track_to_dto
from music_bot.domain.music.models import Track


@pytest.mark.unit
class TestTrackMapper:
    def test_maps_fields(self, make_track: MakeTrack) -> None:
        track: Track = make_track("https://example.com/1.mp3", requested_by=42)

        dto: TrackDto = map_track_to_dto(track)

        assert dto.url == track.url
        assert dto.title == track.title
        assert dto.requested_by == track.requested_by
        assert dto.requested_at == track.requested_at
        assert dto.duration_seconds == track.duration_seconds
