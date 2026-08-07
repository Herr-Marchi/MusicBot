from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self

from .playlist_repository import PlaylistRepository
from .user_repository import UserRepository


class PlaylistUoW(Protocol):
    @property
    def user_repository(self) -> UserRepository: ...

    @property
    def playlist_repository(self) -> PlaylistRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


type PlaylistUoWFactory = Callable[[], PlaylistUoW]
