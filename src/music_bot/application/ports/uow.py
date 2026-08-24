from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self

from music_bot.application.ports.playlists.playlist_repository import PlaylistRepository
from music_bot.application.ports.playlists.user_repository import UserRepository
from music_bot.application.ports.track_repository import TrackRepository


class UoW(Protocol):
    @property
    def user_repository(self) -> UserRepository: ...

    @property
    def playlist_repository(self) -> PlaylistRepository: ...

    @property
    def track_repository(self) -> TrackRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


type UoWFactory = Callable[[], UoW]
