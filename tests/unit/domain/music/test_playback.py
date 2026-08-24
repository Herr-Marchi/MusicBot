from __future__ import annotations

import pytest
from tests.typing_helper import MakeTrack

from music_bot.domain.music.models import GuildPlayback, Track


@pytest.mark.unit
class TestGuildPlayback:
    def test_empty_playback_is_valid(self) -> None:
        playback = GuildPlayback(guild_id=1)

        assert playback.track_count == 0
        assert playback.current_track is None

    def test_current_track_follows_queue_transitions(self, make_track: MakeTrack) -> None:
        first: Track = make_track(url="https://example.com/first")
        second: Track = make_track(url="https://example.com/second")
        playback = GuildPlayback(guild_id=1)

        playback.enqueue(first)
        playback.enqueue(second)
        assert playback.current_track is first

        playback.skip()
        assert playback.current_track is second

        playback.clear()
        assert playback.current_track is None

    def test_skip_resumes_paused_playback(self, make_track: MakeTrack) -> None:
        playback = GuildPlayback(guild_id=1, paused=True)
        playback.enqueue(make_track())

        playback.skip()

        assert playback.is_paused is False
