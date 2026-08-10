from __future__ import annotations

from datetime import UTC, datetime

import pytest

from music_bot.application.contracts.commands.music import (
    NowPlayingCommand,
    PlayUrlCommand,
    SkipCommand,
    StopCommand,
)
from music_bot.domain.music.models import Track
from tests.fakes import FakeTrackSource
from tests.typing_helper import (
    MakeNowPlayingCommand,
    MakePlayUrlCommand,
    MakeSkipCommand,
    MakeStopCommand,
    MakeTrack,
)


@pytest.fixture
def fake_track_source() -> FakeTrackSource:
    return FakeTrackSource()


@pytest.fixture
def make_track() -> MakeTrack:
    def _make_track(url: str = "https://example.com/a.mp3", requested_by: int = 1) -> Track:
        return Track(
            url=url,
            title=url,
            requested_by=requested_by,
            requested_at=datetime.now(UTC),
            duration_seconds=0,
        )

    return _make_track


@pytest.fixture
def make_play_url_command() -> MakePlayUrlCommand:
    def _make_play_url_command(
        guild_id: int = 1,
        url: str = "https://example.com/a.mp3",
        requested_by: int = 1,
        title: str | None = None,
    ) -> PlayUrlCommand:
        return PlayUrlCommand(
            guild_id=guild_id,
            url=url,
            requested_by=requested_by,
            title=title,
        )

    return _make_play_url_command


@pytest.fixture
def make_stop_command() -> MakeStopCommand:
    def _make_stop_command(guild_id: int = 1, requested_by: int = 1) -> StopCommand:
        return StopCommand(
            guild_id=guild_id,
            requested_by=requested_by,
        )

    return _make_stop_command


@pytest.fixture
def make_skip_command() -> MakeSkipCommand:
    def _make_skip_command(guild_id: int = 1, requested_by: int = 1) -> SkipCommand:
        return SkipCommand(
            guild_id=guild_id,
            requested_by=requested_by,
        )

    return _make_skip_command


@pytest.fixture
def make_now_playing_command() -> MakeNowPlayingCommand:
    def _make_now_playing_command(guild_id: int = 1, requested_by: int = 1) -> NowPlayingCommand:
        return NowPlayingCommand(
            guild_id=guild_id,
            requested_by=requested_by,
        )

    return _make_now_playing_command
