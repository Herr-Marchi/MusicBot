from __future__ import annotations

import pytest
from tests.fakes import FakeTrackRepository, FakeTrackSource, FakeUoWFactory

from music_bot.application.orchestration.track_service import TrackService


@pytest.fixture
def fake_uow_factory() -> FakeUoWFactory:
    return FakeUoWFactory()


@pytest.fixture
def fake_track_repository(fake_uow_factory: FakeUoWFactory) -> FakeTrackRepository:
    return fake_uow_factory.track_repository


@pytest.fixture
def track_service(
    fake_track_source: FakeTrackSource,
) -> TrackService:
    return TrackService(source=fake_track_source)
