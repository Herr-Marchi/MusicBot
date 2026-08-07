from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from music_bot.domain.playlists.models import PlaylistAccess


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaylistData:
    id: str
    title: str
    owner_id: int
    access: PlaylistAccess


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackData:
    id: str
    url: str
    title: str
    duration_seconds: int


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaylistTrackData:
    id: str
    track: TrackData
    position: int


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaylistVisibility:
    owner_id: int | None = None
    include_public: bool = False


class PlaylistRepository(Protocol):
    async def get(self, *, playlist_id: str) -> PlaylistData | None: ...

    async def create(
        self,
        *,
        title: str,
        owner_id: int,
        access: PlaylistAccess,
    ) -> PlaylistData: ...

    async def set_title(self, *, playlist_id: str, title: str) -> None: ...

    async def set_access(self, *, playlist_id: str, access: PlaylistAccess) -> None: ...

    async def delete(self, *, playlist_id: str) -> None: ...

    async def list(self, *, visibility: PlaylistVisibility) -> Sequence[PlaylistData]: ...

    async def get_tracks(self, *, playlist_id: str) -> Sequence[PlaylistTrackData]: ...

    async def add_track(
        self,
        *,
        playlist_id: str,
        url: str,
        title: str,
        duration_seconds: int,
    ) -> PlaylistTrackData: ...

    async def remove_track(self, *, playlist_track_id: str) -> None: ...
