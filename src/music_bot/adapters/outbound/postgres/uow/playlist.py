from __future__ import annotations

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from music_bot.adapters.outbound.postgres.repositories import (
    PostgresPlaylistRepository,
    PostgresUserRepository,
)


class PostgresPlaylistUoW:
    def __init__(
        self,
        *,
        session: AsyncSession,
        user_repository: PostgresUserRepository,
        playlist_repository: PostgresPlaylistRepository,
    ) -> None:
        self._session: AsyncSession = session
        self._user_repository: PostgresUserRepository = user_repository
        self._playlist_repository: PostgresPlaylistRepository = playlist_repository

    @property
    def user_repository(self) -> PostgresUserRepository:
        return self._user_repository

    @property
    def playlist_repository(self) -> PostgresPlaylistRepository:
        return self._playlist_repository

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            await self.rollback()
        finally:
            await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


class PostgresPlaylistUoWFactory:
    def __init__(self, *, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory: async_sessionmaker[AsyncSession] = session_factory

    def __call__(self) -> PostgresPlaylistUoW:
        session: AsyncSession = self._session_factory()
        user_repository: PostgresUserRepository = PostgresUserRepository(session=session)
        playlist_repository: PostgresPlaylistRepository = PostgresPlaylistRepository(
            session=session
        )
        return PostgresPlaylistUoW(
            session=session,
            user_repository=user_repository,
            playlist_repository=playlist_repository,
        )
