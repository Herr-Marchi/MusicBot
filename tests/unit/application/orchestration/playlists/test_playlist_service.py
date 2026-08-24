from __future__ import annotations

from collections.abc import Sequence

import pytest
from tests.fakes import FakeTrackSource, FakeUoWFactory

from music_bot.application.contracts.errors import NotPlaylistOwnerError, PlaylistNotFoundError
from music_bot.application.orchestration.playlists.service import PlaylistService
from music_bot.application.ports.playlists import PlaylistData, PlaylistEntry
from music_bot.domain.playlists.models import PlaylistAccess

OWNER_ID = 1
OTHER_USER_ID = 2


@pytest.mark.unit
class TestCreate:
    async def test_create_persists_playlist_and_upserts_owner(
        self,
        playlist_service: PlaylistService,
        fake_uow_factory: FakeUoWFactory,
    ) -> None:
        playlist: PlaylistData = await playlist_service.create(
            owner_id=OWNER_ID,
            owner_username="alice",
            title="Chill Mix",
            access=PlaylistAccess.PRIVATE,
        )

        assert playlist.title == "Chill Mix"
        assert playlist.owner_id == OWNER_ID
        assert fake_uow_factory.user_repository.upsert_calls == [(OWNER_ID, "alice")]

        stored: PlaylistData | None = await fake_uow_factory.playlist_repository.get(
            playlist_id=playlist.id
        )
        assert stored == playlist


@pytest.mark.unit
class TestOwnershipEnforcement:
    async def test_rename_by_owner_succeeds(self, playlist_service: PlaylistService) -> None:
        playlist: PlaylistData = await playlist_service.create(
            owner_id=OWNER_ID, owner_username="alice", title="Old", access=PlaylistAccess.PRIVATE
        )

        renamed: PlaylistData = await playlist_service.rename(
            playlist_id=playlist.id, requested_by=OWNER_ID, title="New"
        )

        assert renamed.title == "New"

    async def test_rename_by_non_owner_on_private_playlist_raises_not_found(
        self, playlist_service: PlaylistService
    ) -> None:
        playlist: PlaylistData = await playlist_service.create(
            owner_id=OWNER_ID, owner_username="alice", title="Old", access=PlaylistAccess.PRIVATE
        )

        with pytest.raises(PlaylistNotFoundError):
            await playlist_service.rename(
                playlist_id=playlist.id, requested_by=OTHER_USER_ID, title="Stolen"
            )

    async def test_rename_by_non_owner_on_public_playlist_raises_not_owner(
        self, playlist_service: PlaylistService
    ) -> None:
        playlist: PlaylistData = await playlist_service.create(
            owner_id=OWNER_ID, owner_username="alice", title="Old", access=PlaylistAccess.PUBLIC
        )

        with pytest.raises(NotPlaylistOwnerError):
            await playlist_service.rename(
                playlist_id=playlist.id, requested_by=OTHER_USER_ID, title="Stolen"
            )

    async def test_delete_by_non_owner_on_private_playlist_raises_not_found(
        self, playlist_service: PlaylistService
    ) -> None:
        playlist: PlaylistData = await playlist_service.create(
            owner_id=OWNER_ID, owner_username="alice", title="Mine", access=PlaylistAccess.PRIVATE
        )

        with pytest.raises(PlaylistNotFoundError):
            await playlist_service.delete(playlist_id=playlist.id, requested_by=OTHER_USER_ID)

    async def test_add_track_by_non_owner_on_public_playlist_raises_not_owner(
        self, playlist_service: PlaylistService
    ) -> None:
        playlist: PlaylistData = await playlist_service.create(
            owner_id=OWNER_ID, owner_username="alice", title="Mine", access=PlaylistAccess.PUBLIC
        )

        with pytest.raises(NotPlaylistOwnerError):
            await playlist_service.add_track(
                playlist_id=playlist.id,
                requested_by=OTHER_USER_ID,
                url="https://example.com/a.mp3",
            )

    async def test_add_track_by_non_owner_on_private_playlist_raises_not_found(
        self, playlist_service: PlaylistService
    ) -> None:
        playlist: PlaylistData = await playlist_service.create(
            owner_id=OWNER_ID, owner_username="alice", title="Mine", access=PlaylistAccess.PRIVATE
        )

        with pytest.raises(PlaylistNotFoundError):
            await playlist_service.add_track(
                playlist_id=playlist.id,
                requested_by=OTHER_USER_ID,
                url="https://example.com/a.mp3",
            )

    async def test_operation_on_missing_playlist_raises_not_found(
        self, playlist_service: PlaylistService
    ) -> None:
        with pytest.raises(PlaylistNotFoundError):
            await playlist_service.rename(
                playlist_id="does-not-exist", requested_by=OWNER_ID, title="X"
            )


@pytest.mark.unit
class TestDelete:
    async def test_delete_removes_playlist(
        self,
        playlist_service: PlaylistService,
        fake_uow_factory: FakeUoWFactory,
    ) -> None:
        playlist: PlaylistData = await playlist_service.create(
            owner_id=OWNER_ID, owner_username="alice", title="Gone", access=PlaylistAccess.PRIVATE
        )

        await playlist_service.delete(playlist_id=playlist.id, requested_by=OWNER_ID)

        assert await fake_uow_factory.playlist_repository.get(playlist_id=playlist.id) is None


@pytest.mark.unit
class TestVisibilityListing:
    async def test_list_editable_returns_only_own_playlists(
        self, playlist_service: PlaylistService
    ) -> None:
        await playlist_service.create(
            owner_id=OWNER_ID, owner_username="alice", title="Mine", access=PlaylistAccess.PRIVATE
        )
        await playlist_service.create(
            owner_id=OTHER_USER_ID,
            owner_username="bob",
            title="Theirs",
            access=PlaylistAccess.PUBLIC,
        )

        editable: Sequence[PlaylistData] = await playlist_service.list_editable(user_id=OWNER_ID)

        assert [p.title for p in editable] == ["Mine"]

    async def test_list_readable_includes_own_and_public_playlists(
        self, playlist_service: PlaylistService
    ) -> None:
        await playlist_service.create(
            owner_id=OWNER_ID,
            owner_username="alice",
            title="Mine Private",
            access=PlaylistAccess.PRIVATE,
        )
        await playlist_service.create(
            owner_id=OTHER_USER_ID,
            owner_username="bob",
            title="Their Public",
            access=PlaylistAccess.PUBLIC,
        )
        await playlist_service.create(
            owner_id=OTHER_USER_ID,
            owner_username="bob",
            title="Their Private",
            access=PlaylistAccess.PRIVATE,
        )

        readable: Sequence[PlaylistData] = await playlist_service.list_readable(user_id=OWNER_ID)

        assert {p.title for p in readable} == {"Mine Private", "Their Public"}


@pytest.mark.unit
class TestTracks:
    async def test_add_track_resolves_metadata_and_appends(
        self,
        playlist_service: PlaylistService,
        fake_track_source: FakeTrackSource,
        fake_uow_factory: FakeUoWFactory,
    ) -> None:
        fake_track_source.set_metadata(
            "https://example.com/a.mp3", title="Song A", duration_seconds=180
        )
        playlist: PlaylistData = await playlist_service.create(
            owner_id=OWNER_ID, owner_username="alice", title="Mix", access=PlaylistAccess.PRIVATE
        )
        uow_count_before_add: int = len(fake_uow_factory.uows)

        track: PlaylistEntry = await playlist_service.add_track(
            playlist_id=playlist.id,
            requested_by=OWNER_ID,
            url="https://example.com/a.mp3",
        )

        assert track.track.title == "Song A"
        assert track.track.duration_seconds == 180
        assert track.position == 0
        assert len(fake_uow_factory.uows) == uow_count_before_add + 1
        assert fake_uow_factory.uows[-1].commit_calls == 1

    async def test_second_track_appends_after_first(
        self,
        playlist_service: PlaylistService,
        fake_track_source: FakeTrackSource,
    ) -> None:
        fake_track_source.set_metadata("https://example.com/a.mp3", title="Song A")
        fake_track_source.set_metadata("https://example.com/b.mp3", title="Song B")
        playlist: PlaylistData = await playlist_service.create(
            owner_id=OWNER_ID, owner_username="alice", title="Mix", access=PlaylistAccess.PRIVATE
        )

        await playlist_service.add_track(
            playlist_id=playlist.id, requested_by=OWNER_ID, url="https://example.com/a.mp3"
        )
        second: PlaylistEntry = await playlist_service.add_track(
            playlist_id=playlist.id, requested_by=OWNER_ID, url="https://example.com/b.mp3"
        )

        assert second.position == 1

    async def test_remove_track_by_position(
        self,
        playlist_service: PlaylistService,
        fake_track_source: FakeTrackSource,
    ) -> None:
        fake_track_source.set_metadata("https://example.com/a.mp3", title="Song A")
        playlist: PlaylistData = await playlist_service.create(
            owner_id=OWNER_ID, owner_username="alice", title="Mix", access=PlaylistAccess.PRIVATE
        )
        await playlist_service.add_track(
            playlist_id=playlist.id, requested_by=OWNER_ID, url="https://example.com/a.mp3"
        )

        await playlist_service.remove_track(
            playlist_id=playlist.id, requested_by=OWNER_ID, position=0
        )

        detail = await playlist_service.get(playlist_id=playlist.id, requested_by=OWNER_ID)
        assert detail.tracks == []

    async def test_remove_track_missing_position_raises(
        self, playlist_service: PlaylistService
    ) -> None:
        playlist: PlaylistData = await playlist_service.create(
            owner_id=OWNER_ID, owner_username="alice", title="Mix", access=PlaylistAccess.PRIVATE
        )

        with pytest.raises(PlaylistNotFoundError):
            await playlist_service.remove_track(
                playlist_id=playlist.id, requested_by=OWNER_ID, position=0
            )

    async def test_get_returns_playlist_and_tracks(
        self,
        playlist_service: PlaylistService,
        fake_track_source: FakeTrackSource,
    ) -> None:
        fake_track_source.set_metadata("https://example.com/a.mp3", title="Song A")
        playlist: PlaylistData = await playlist_service.create(
            owner_id=OWNER_ID, owner_username="alice", title="Mix", access=PlaylistAccess.PRIVATE
        )
        await playlist_service.add_track(
            playlist_id=playlist.id, requested_by=OWNER_ID, url="https://example.com/a.mp3"
        )

        detail = await playlist_service.get(playlist_id=playlist.id, requested_by=OWNER_ID)

        assert detail.playlist.id == playlist.id
        assert [t.track.title for t in detail.tracks] == ["Song A"]

    async def test_get_by_non_owner_on_private_playlist_raises_not_found(
        self, playlist_service: PlaylistService
    ) -> None:
        playlist: PlaylistData = await playlist_service.create(
            owner_id=OWNER_ID, owner_username="alice", title="Mine", access=PlaylistAccess.PRIVATE
        )

        with pytest.raises(PlaylistNotFoundError):
            await playlist_service.get(playlist_id=playlist.id, requested_by=OTHER_USER_ID)

    async def test_get_by_non_owner_on_public_playlist_succeeds(
        self, playlist_service: PlaylistService
    ) -> None:
        playlist: PlaylistData = await playlist_service.create(
            owner_id=OWNER_ID, owner_username="alice", title="Open", access=PlaylistAccess.PUBLIC
        )

        detail = await playlist_service.get(playlist_id=playlist.id, requested_by=OTHER_USER_ID)

        assert detail.playlist.id == playlist.id
