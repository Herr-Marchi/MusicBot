from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest

from music_bot.application.contracts.commands.music import (
    PlayPlaylistCommand,
    PlayUrlCommand,
)
from music_bot.application.contracts.dto import QueuedTrackDto
from music_bot.application.contracts.results.music import (
    PlayPlaylistResult,
    PlayUrlResult,
)
from music_bot.application.orchestration.music.handlers import (
    HandlerOutcome,
    PlayPlaylistCommandHandler,
)
from music_bot.application.orchestration.playlists import PlaylistDetail, PlaylistService
from music_bot.application.ports.playlists import PlaylistData, PlaylistEntry
from music_bot.application.ports.track import StoredTrack
from music_bot.domain.playlists.models import PlaylistAccess


def _play_url_result(*, command: PlayUrlCommand, queue_size: int) -> PlayUrlResult:
    return PlayUrlResult(
        track=QueuedTrackDto(
            url=command.url,
            title=command.url,
            requested_by=command.requested_by,
            requested_at=datetime.now(UTC),
            duration_seconds=1,
        ),
        queue_size=queue_size,
    )


class StubPlayUrlCommandHandler:
    def __init__(self, *, initial_queue_size: int = 0, broken_url: str | None = None) -> None:
        self._initial_queue_size: int = initial_queue_size
        self._broken_url: str | None = broken_url
        self.commands: list[PlayUrlCommand] = []

    async def handle(self, command: PlayUrlCommand) -> HandlerOutcome[PlayUrlResult]:
        self.commands.append(command)
        if command.url == self._broken_url:
            raise RuntimeError("broken track")

        return HandlerOutcome(
            result=_play_url_result(
                command=command,
                queue_size=self._initial_queue_size + len(self.commands),
            ),
            mutated=True,
            interrupts_current_track=False,
            restart_playback=False,
        )


class StubPlaylistService:
    def __init__(self, *, detail: PlaylistDetail) -> None:
        self._detail: PlaylistDetail = detail
        self.get_calls: list[tuple[str, int]] = []

    async def get(self, *, playlist_id: str, requested_by: int) -> PlaylistDetail:
        self.get_calls.append((playlist_id, requested_by))
        return self._detail


def _playlist_detail(*urls: str) -> PlaylistDetail:
    return PlaylistDetail(
        playlist=PlaylistData(
            id="playlist-1",
            title="Playlist",
            owner_id=2,
            access=PlaylistAccess.PRIVATE,
        ),
        tracks=tuple(
            PlaylistEntry(
                id=f"entry-{position}",
                track=StoredTrack(
                    id=f"track-{position}",
                    url=url,
                    title=url,
                    duration_seconds=1,
                ),
                position=position,
            )
            for position, url in enumerate(urls)
        ),
    )


@pytest.mark.unit
class TestPlayPlaylistCommandHandler:
    async def test_empty_playlist_does_not_mutate_playback(self) -> None:
        play_url_handler = StubPlayUrlCommandHandler()
        playlist_service = StubPlaylistService(detail=_playlist_detail())

        outcome: HandlerOutcome[PlayPlaylistResult] = await PlayPlaylistCommandHandler(
            playlist_service=cast(PlaylistService, playlist_service),
            play_url_handler=play_url_handler,
        ).handle(
            PlayPlaylistCommand(
                guild_id=1,
                requested_by=2,
                playlist_id="playlist-1",
            )
        )

        assert play_url_handler.commands == []
        assert outcome.result == PlayPlaylistResult(
            playlist_title="Playlist",
            queued_count=0,
            started_playing=False,
        )
        assert outcome.mutated is False

    async def test_enqueues_tracks_in_order(self) -> None:
        play_url_handler = StubPlayUrlCommandHandler()
        playlist_service = StubPlaylistService(
            detail=_playlist_detail(
                "https://example.com/first",
                "https://example.com/second",
            )
        )

        outcome: HandlerOutcome[PlayPlaylistResult] = await PlayPlaylistCommandHandler(
            playlist_service=cast(PlaylistService, playlist_service),
            play_url_handler=play_url_handler,
        ).handle(
            PlayPlaylistCommand(
                guild_id=1,
                requested_by=2,
                playlist_id="playlist-1",
            )
        )

        assert [command.url for command in play_url_handler.commands] == [
            "https://example.com/first",
            "https://example.com/second",
        ]
        assert playlist_service.get_calls == [("playlist-1", 2)]
        assert outcome.result == PlayPlaylistResult(
            playlist_title="Playlist",
            queued_count=2,
            started_playing=True,
        )
        assert outcome.mutated is True

    async def test_stops_on_first_failed_track(self) -> None:
        play_url_handler = StubPlayUrlCommandHandler(broken_url="https://example.com/broken")
        playlist_service = StubPlaylistService(
            detail=_playlist_detail(
                "https://example.com/first",
                "https://example.com/broken",
                "https://example.com/never-reached",
            )
        )

        with pytest.raises(RuntimeError, match="broken track"):
            await PlayPlaylistCommandHandler(
                playlist_service=cast(PlaylistService, playlist_service),
                play_url_handler=play_url_handler,
            ).handle(
                PlayPlaylistCommand(
                    guild_id=1,
                    requested_by=2,
                    playlist_id="playlist-1",
                )
            )

        assert [command.url for command in play_url_handler.commands] == [
            "https://example.com/first",
            "https://example.com/broken",
        ]
