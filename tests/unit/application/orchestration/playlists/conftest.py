from __future__ import annotations

import pytest
from tests.fakes import FakeUoWFactory

from music_bot.application.orchestration.playlists.service import PlaylistService
from music_bot.application.orchestration.track_service import TrackService


@pytest.fixture
def fake_uow_factory() -> FakeUoWFactory:
    return FakeUoWFactory()


@pytest.fixture
def playlist_service(
    fake_uow_factory: FakeUoWFactory,
    track_service: TrackService,
) -> PlaylistService:
    return PlaylistService(uow_factory=fake_uow_factory, track_service=track_service)
