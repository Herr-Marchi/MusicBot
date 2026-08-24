from __future__ import annotations

import uuid

import pytest
from tests.fakes import FakeTrackSource

from music_bot.adapters.outbound.postgres import PostgresUoWFactory
from music_bot.application.contracts.errors import NotPlaylistOwnerError, PlaylistNotFoundError
from music_bot.application.orchestration.playlists import PlaylistDetail
from music_bot.application.orchestration.playlists.service import PlaylistService
from music_bot.application.orchestration.track_service import TrackService
from music_bot.application.ports.playlists import PlaylistData
from music_bot.application.ports.track import StoredTrack
from music_bot.domain.playlists.models import PlaylistAccess


def _unique_user_id() -> int:
    return uuid.uuid4().int % 1_000_000_000


@pytest.fixture
def playlist_service(
    postgres_uow_factory: PostgresUoWFactory,
    fake_track_source: FakeTrackSource,
) -> PlaylistService:
    track_service: TrackService = TrackService(source=fake_track_source)
    return PlaylistService(uow_factory=postgres_uow_factory, track_service=track_service)


@pytest.mark.integration
class TestPlaylistLifecycleAgainstRealPostgres:
    async def test_create_add_remove_and_delete_use_case(
        self,
        playlist_service: PlaylistService,
        fake_track_source: FakeTrackSource,
    ) -> None:
        owner_id: int = _unique_user_id()
        fake_track_source.set_metadata(
            "https://example.com/a.mp3", title="Song A", duration_seconds=120
        )
        fake_track_source.set_metadata(
            "https://example.com/b.mp3", title="Song B", duration_seconds=90
        )

        playlist: PlaylistData = await playlist_service.create(
            owner_id=owner_id,
            owner_username="integration-user",
            title="Road Trip",
            access=PlaylistAccess.PRIVATE,
        )
        await playlist_service.add_track(
            playlist_id=playlist.id, requested_by=owner_id, url="https://example.com/a.mp3"
        )
        await playlist_service.add_track(
            playlist_id=playlist.id, requested_by=owner_id, url="https://example.com/b.mp3"
        )

        detail: PlaylistDetail = await playlist_service.get(
            playlist_id=playlist.id, requested_by=owner_id
        )
        assert detail.playlist.title == "Road Trip"
        assert [t.track.title for t in detail.tracks] == ["Song A", "Song B"]
        assert [t.position for t in detail.tracks] == [0, 1]

        await playlist_service.remove_track(
            playlist_id=playlist.id, requested_by=owner_id, position=0
        )
        remaining: PlaylistDetail = await playlist_service.get(
            playlist_id=playlist.id, requested_by=owner_id
        )
        assert [t.track.title for t in remaining.tracks] == ["Song B"]
        assert remaining.tracks[0].position == 0

        await playlist_service.delete(playlist_id=playlist.id, requested_by=owner_id)
        with pytest.raises(PlaylistNotFoundError):
            await playlist_service.get(playlist_id=playlist.id, requested_by=owner_id)

    async def test_private_playlist_not_readable_by_non_owner_via_direct_id(
        self, playlist_service: PlaylistService
    ) -> None:
        owner_id: int = _unique_user_id()
        other_id: int = _unique_user_id()
        playlist: PlaylistData = await playlist_service.create(
            owner_id=owner_id,
            owner_username="owner",
            title="Secret",
            access=PlaylistAccess.PRIVATE,
        )

        with pytest.raises(PlaylistNotFoundError):
            await playlist_service.get(playlist_id=playlist.id, requested_by=other_id)

        await playlist_service.delete(playlist_id=playlist.id, requested_by=owner_id)

    async def test_ownership_enforced_against_real_database(
        self, playlist_service: PlaylistService
    ) -> None:
        owner_id: int = _unique_user_id()
        other_id: int = _unique_user_id()
        private: PlaylistData = await playlist_service.create(
            owner_id=owner_id, owner_username="owner", title="Mine", access=PlaylistAccess.PRIVATE
        )
        public: PlaylistData = await playlist_service.create(
            owner_id=owner_id, owner_username="owner", title="Open", access=PlaylistAccess.PUBLIC
        )

        with pytest.raises(PlaylistNotFoundError):
            await playlist_service.rename(
                playlist_id=private.id, requested_by=other_id, title="Stolen"
            )
        with pytest.raises(NotPlaylistOwnerError):
            await playlist_service.rename(
                playlist_id=public.id, requested_by=other_id, title="Stolen"
            )

        await playlist_service.delete(playlist_id=private.id, requested_by=owner_id)
        await playlist_service.delete(playlist_id=public.id, requested_by=owner_id)

    async def test_list_readable_or_clause_against_real_database(
        self, playlist_service: PlaylistService
    ) -> None:
        owner_id: int = _unique_user_id()
        other_id: int = _unique_user_id()
        mine: PlaylistData = await playlist_service.create(
            owner_id=owner_id,
            owner_username="me",
            title="Mine Private",
            access=PlaylistAccess.PRIVATE,
        )
        theirs_public: PlaylistData = await playlist_service.create(
            owner_id=other_id,
            owner_username="them",
            title="Their Public",
            access=PlaylistAccess.PUBLIC,
        )
        theirs_private: PlaylistData = await playlist_service.create(
            owner_id=other_id,
            owner_username="them",
            title="Their Private",
            access=PlaylistAccess.PRIVATE,
        )

        readable = await playlist_service.list_readable(user_id=owner_id)
        titles = {p.title for p in readable}

        assert "Mine Private" in titles
        assert "Their Public" in titles
        assert "Their Private" not in titles

        for created in (mine, theirs_public, theirs_private):
            await playlist_service.delete(playlist_id=created.id, requested_by=created.owner_id)

    async def test_deleting_playlist_does_not_delete_track(
        self,
        playlist_service: PlaylistService,
        fake_track_source: FakeTrackSource,
        postgres_uow_factory: PostgresUoWFactory,
    ) -> None:
        owner_id: int = _unique_user_id()
        url = f"https://example.com/{uuid.uuid4()}.mp3"
        fake_track_source.set_metadata(url, title="Shared Track", duration_seconds=200)

        playlist: PlaylistData = await playlist_service.create(
            owner_id=owner_id, owner_username="me", title="Temp", access=PlaylistAccess.PRIVATE
        )
        await playlist_service.add_track(playlist_id=playlist.id, requested_by=owner_id, url=url)
        await playlist_service.delete(playlist_id=playlist.id, requested_by=owner_id)

        async with postgres_uow_factory() as uow:
            stored: StoredTrack | None = await uow.track_repository.get_by_url(url=url)

        assert stored is not None
        assert stored.title == "Shared Track"
