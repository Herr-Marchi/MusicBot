from __future__ import annotations

import pytest
from tests.fakes import FakeTrackCatalog, FakeTrackSource

from music_bot.application.orchestration.track_metadata_resolver import (
    CatalogBackedTrackMetadataResolver,
)
from music_bot.application.ports.track_source import TrackMetadata


@pytest.mark.unit
class TestCatalogBackedTrackMetadataResolver:
    async def test_cache_hit_skips_inner_resolver(
        self,
        fake_track_catalog: FakeTrackCatalog,
        fake_track_source: FakeTrackSource,
        resolver: CatalogBackedTrackMetadataResolver,
    ) -> None:
        fake_track_catalog.seed(
            "https://example.com/a.mp3", title="Cached Song", duration_seconds=200
        )

        metadata: TrackMetadata = await resolver.resolve(source_url="https://example.com/a.mp3")

        assert metadata.title == "Cached Song"
        assert metadata.duration_seconds == 200
        assert fake_track_source.resolve_calls == []

    async def test_cache_miss_falls_through_and_populates_catalog(
        self,
        fake_track_catalog: FakeTrackCatalog,
        fake_track_source: FakeTrackSource,
        resolver: CatalogBackedTrackMetadataResolver,
    ) -> None:
        fake_track_source.set_metadata(
            "https://example.com/b.mp3", title="Fresh Song", duration_seconds=150
        )

        metadata: TrackMetadata = await resolver.resolve(source_url="https://example.com/b.mp3")

        assert metadata.title == "Fresh Song"
        assert fake_track_source.resolve_calls == ["https://example.com/b.mp3"]
        assert fake_track_catalog.upsert_calls == [("https://example.com/b.mp3", "Fresh Song", 150)]
