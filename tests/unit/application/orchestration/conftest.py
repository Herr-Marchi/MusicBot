from __future__ import annotations

import pytest
from tests.fakes import FakeTrackCatalog, FakeTrackSource

from music_bot.application.orchestration.track_metadata_resolver import (
    CatalogBackedTrackMetadataResolver,
)


@pytest.fixture
def fake_track_catalog() -> FakeTrackCatalog:
    return FakeTrackCatalog()


@pytest.fixture
def resolver(
    fake_track_source: FakeTrackSource,
    fake_track_catalog: FakeTrackCatalog,
) -> CatalogBackedTrackMetadataResolver:
    return CatalogBackedTrackMetadataResolver(inner=fake_track_source, catalog=fake_track_catalog)
