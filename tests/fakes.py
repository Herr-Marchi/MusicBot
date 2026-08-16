from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType
from typing import Self

from music_bot.application.ports.music_player import TrackFinishedCallback
from music_bot.application.ports.playlists import (
    DiscordUserData,
    PlaylistData,
    PlaylistTrackData,
    PlaylistVisibility,
    TrackData,
)
from music_bot.application.ports.track_catalog import CatalogedTrack
from music_bot.application.ports.track_source import TrackMetadata
from music_bot.domain.playlists.models import PlaylistAccess


class FakeGuildPlayer:
    def __init__(self) -> None:
        self.play_calls: list[tuple[str, int]] = []
        self.stop_calls: int = 0
        self.pause_calls: int = 0
        self.resume_calls: int = 0
        self.volume_calls: list[int] = []
        self.on_finished_callback: TrackFinishedCallback | None = None

    async def play(
        self,
        *,
        url: str,
        volume: int,
        on_finished: TrackFinishedCallback,
    ) -> None:
        self.play_calls.append((url, volume))
        self.on_finished_callback = on_finished

    async def stop(self) -> None:
        self.stop_calls += 1

    async def pause(self) -> None:
        self.pause_calls += 1

    async def resume(self) -> None:
        self.resume_calls += 1

    async def set_volume(self, volume: int) -> None:
        self.volume_calls.append(volume)

    def finish_current_track(self, exception: Exception | None = None) -> None:
        if self.on_finished_callback is None:
            raise RuntimeError("FakeGuildPlayer has no track currently playing")

        callback: TrackFinishedCallback = self.on_finished_callback
        self.on_finished_callback = None
        callback(exception)


class FakeTrackSource:
    def __init__(self) -> None:
        self.resolve_calls: list[str] = []
        self.resolve_stream_calls: list[str] = []
        self._metadata_by_url: dict[str, TrackMetadata] = {}
        self._resolve_error: Exception | None = None

    def set_metadata(
        self,
        source_url: str,
        *,
        title: str,
        duration_seconds: int = 100,
        canonical_url: str | None = None,
    ) -> None:
        self._metadata_by_url[source_url] = TrackMetadata(
            source_url=canonical_url or source_url,
            title=title,
            duration_seconds=duration_seconds,
        )

    def fail_resolve_with(self, error: Exception) -> None:
        self._resolve_error = error

    async def resolve(self, *, source_url: str) -> TrackMetadata:
        self.resolve_calls.append(source_url)

        if self._resolve_error is not None:
            raise self._resolve_error

        return self._metadata_by_url.get(source_url) or TrackMetadata(
            source_url=source_url,
            title=source_url,
            duration_seconds=100,
        )

    async def resolve_stream(self, *, source_url: str) -> str:
        self.resolve_stream_calls.append(source_url)
        return f"{source_url}#stream"


class FakeTrackCatalog:
    def __init__(self) -> None:
        self.get_calls: list[str] = []
        self.upsert_calls: list[tuple[str, str, int]] = []
        self._by_url: dict[str, CatalogedTrack] = {}

    def seed(self, url: str, *, title: str, duration_seconds: int) -> None:
        self._by_url[url] = CatalogedTrack(url=url, title=title, duration_seconds=duration_seconds)

    async def get(self, *, url: str) -> CatalogedTrack | None:
        self.get_calls.append(url)
        return self._by_url.get(url)

    async def upsert(self, *, url: str, title: str, duration_seconds: int) -> CatalogedTrack:
        self.upsert_calls.append((url, title, duration_seconds))
        cataloged = CatalogedTrack(url=url, title=title, duration_seconds=duration_seconds)
        self._by_url[url] = cataloged
        return cataloged


class FakePlaylistRepository:
    def __init__(self) -> None:
        self._playlists: dict[str, PlaylistData] = {}
        self._tracks: dict[str, list[PlaylistTrackData]] = {}
        self._next_id: int = 1

    def _fresh_id(self) -> str:
        playlist_id: str = str(self._next_id)
        self._next_id += 1
        return playlist_id

    async def get(self, *, playlist_id: str) -> PlaylistData | None:
        return self._playlists.get(playlist_id)

    async def create(
        self,
        *,
        title: str,
        owner_id: int,
        access: PlaylistAccess,
    ) -> PlaylistData:
        playlist_id: str = self._fresh_id()
        playlist = PlaylistData(id=playlist_id, title=title, owner_id=owner_id, access=access)
        self._playlists[playlist_id] = playlist
        self._tracks[playlist_id] = []
        return playlist

    async def set_title(self, *, playlist_id: str, title: str) -> None:
        current: PlaylistData = self._playlists[playlist_id]
        self._playlists[playlist_id] = PlaylistData(
            id=current.id, title=title, owner_id=current.owner_id, access=current.access
        )

    async def set_access(self, *, playlist_id: str, access: PlaylistAccess) -> None:
        current: PlaylistData = self._playlists[playlist_id]
        self._playlists[playlist_id] = PlaylistData(
            id=current.id, title=current.title, owner_id=current.owner_id, access=access
        )

    async def delete(self, *, playlist_id: str) -> None:
        self._playlists.pop(playlist_id, None)
        self._tracks.pop(playlist_id, None)

    async def list(self, *, visibility: PlaylistVisibility) -> Sequence[PlaylistData]:
        result: list[PlaylistData] = []
        for playlist in self._playlists.values():
            owned: bool = (
                visibility.owner_id is not None and playlist.owner_id == visibility.owner_id
            )
            public: bool = visibility.include_public and playlist.access == PlaylistAccess.PUBLIC
            if owned or public:
                result.append(playlist)
        return result

    async def get_tracks(self, *, playlist_id: str) -> Sequence[PlaylistTrackData]:
        return list(self._tracks.get(playlist_id, []))

    async def add_track(
        self,
        *,
        playlist_id: str,
        url: str,
        title: str,
        duration_seconds: int,
    ) -> PlaylistTrackData:
        track_id: str = self._fresh_id()
        playlist_track = PlaylistTrackData(
            id=track_id,
            track=TrackData(id=track_id, url=url, title=title, duration_seconds=duration_seconds),
            position=len(self._tracks.get(playlist_id, [])),
        )
        self._tracks[playlist_id].append(playlist_track)
        return playlist_track

    async def remove_track(self, *, playlist_track_id: str) -> None:
        for playlist_id, tracks in self._tracks.items():
            self._tracks[playlist_id] = [t for t in tracks if t.id != playlist_track_id]


class FakeUserRepository:
    def __init__(self) -> None:
        self.upsert_calls: list[tuple[int, str]] = []
        self._users: dict[int, DiscordUserData] = {}

    async def get(self, *, user_id: int) -> DiscordUserData | None:
        return self._users.get(user_id)

    async def upsert(self, *, user_id: int, username: str) -> DiscordUserData:
        self.upsert_calls.append((user_id, username))
        user = DiscordUserData(id=user_id, username=username)
        self._users[user_id] = user
        return user


class FakePlaylistUoW:
    def __init__(
        self,
        *,
        playlist_repository: FakePlaylistRepository,
        user_repository: FakeUserRepository,
    ) -> None:
        self.playlist_repository: FakePlaylistRepository = playlist_repository
        self.user_repository: FakeUserRepository = user_repository
        self.commit_calls: int = 0
        self.rollback_calls: int = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        pass

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:
        self.rollback_calls += 1


class FakePlaylistUoWFactory:
    def __init__(self) -> None:
        self.playlist_repository: FakePlaylistRepository = FakePlaylistRepository()
        self.user_repository: FakeUserRepository = FakeUserRepository()
        self.uows: list[FakePlaylistUoW] = []

    def __call__(self) -> FakePlaylistUoW:
        uow = FakePlaylistUoW(
            playlist_repository=self.playlist_repository,
            user_repository=self.user_repository,
        )
        self.uows.append(uow)
        return uow
