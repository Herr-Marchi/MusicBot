from __future__ import annotations

import pytest
from tests.fakes import FakeTrackRepository, FakeTrackSource

from music_bot.application.orchestration.track_service import TrackService
from music_bot.application.ports.track import StoredTrack


@pytest.mark.unit
class TestTrackService:
    async def test_existing_track_skips_the_source(
        self,
        fake_track_repository: FakeTrackRepository,
        fake_track_source: FakeTrackSource,
        track_service: TrackService,
    ) -> None:
        fake_track_repository.seed(
            "https://example.com/a.mp3", title="Stored Song", duration_seconds=200
        )

        track: StoredTrack = await track_service.get_or_register(
            url="https://example.com/a.mp3",
            repository=fake_track_repository,
        )

        assert track.title == "Stored Song"
        assert fake_track_source.resolve_calls == []

    async def test_missing_track_is_resolved_and_saved(
        self,
        fake_track_repository: FakeTrackRepository,
        fake_track_source: FakeTrackSource,
        track_service: TrackService,
    ) -> None:
        fake_track_source.set_metadata(
            "https://example.com/b.mp3", title="Fresh Song", duration_seconds=150
        )

        track: StoredTrack = await track_service.get_or_register(
            url="https://example.com/b.mp3",
            repository=fake_track_repository,
        )

        assert track.title == "Fresh Song"
        assert fake_track_source.resolve_calls == ["https://example.com/b.mp3"]
        assert fake_track_repository.save_calls == [
            ("https://example.com/b.mp3", "Fresh Song", 150)
        ]
