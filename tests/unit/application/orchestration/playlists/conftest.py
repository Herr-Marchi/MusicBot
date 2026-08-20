from __future__ import annotations

import pytest
from tests.fakes import FakePlaylistUoWFactory, FakeTrackSource

from music_bot.application.orchestration.playlists.service import PlaylistService


@pytest.fixture
def fake_uow_factory() -> FakePlaylistUoWFactory:
    return FakePlaylistUoWFactory()


@pytest.fixture
def playlist_service(
    fake_uow_factory: FakePlaylistUoWFactory,
    fake_track_source: FakeTrackSource,
) -> PlaylistService:
    return PlaylistService(uow_factory=fake_uow_factory, metadata_resolver=fake_track_source)
