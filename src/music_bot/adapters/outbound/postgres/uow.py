from __future__ import annotations

import logging
from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from music_bot.adapters.outbound.postgres.repositories import (
    PostgresPlaylistRepository,
    PostgresTrackRepository,
    PostgresUserRepository,
)

logger: logging.Logger = logging.getLogger(__name__)


class PostgresUoW:
    def __init__(
        self,
        *,
        session: AsyncSession,
        user_repository: PostgresUserRepository,
        playlist_repository: PostgresPlaylistRepository,
        track_repository: PostgresTrackRepository,
    ) -> None:
        self._session: AsyncSession = session
        self._user_repository: PostgresUserRepository = user_repository
        self._playlist_repository: PostgresPlaylistRepository = playlist_repository
        self._track_repository: PostgresTrackRepository = track_repository

    @property
    def user_repository(self) -> PostgresUserRepository:
        return self._user_repository

    @property
    def playlist_repository(self) -> PostgresPlaylistRepository:
        return self._playlist_repository

    @property
    def track_repository(self) -> PostgresTrackRepository:
        return self._track_repository

    async def __aenter__(self) -> Self:
        logger.debug("Postgres UoW entered session_id=%s", id(self._session))
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exception is None:
            logger.debug("Postgres UoW exiting session_id=%s", id(self._session))
        else:
            logger.warning(
                "Postgres UoW exiting with error session_id=%s error_type=%s",
                id(self._session),
                type(exception).__name__,
            )
        try:
            await self.rollback()
        finally:
            await self._session.close()
            logger.debug("Postgres session closed session_id=%s", id(self._session))

    async def commit(self) -> None:
        logger.info("Postgres transaction commit started session_id=%s", id(self._session))
        await self._session.commit()
        logger.info("Postgres transaction committed session_id=%s", id(self._session))

    async def rollback(self) -> None:
        logger.debug("Postgres transaction rollback started session_id=%s", id(self._session))
        await self._session.rollback()
        logger.debug("Postgres transaction rolled back session_id=%s", id(self._session))


class PostgresUoWFactory:
    def __init__(self, *, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory: async_sessionmaker[AsyncSession] = session_factory

    def __call__(self) -> PostgresUoW:
        session: AsyncSession = self._session_factory()
        logger.debug("Postgres UoW created session_id=%s", id(session))
        return PostgresUoW(
            session=session,
            user_repository=PostgresUserRepository(session=session),
            playlist_repository=PostgresPlaylistRepository(session=session),
            track_repository=PostgresTrackRepository(session=session),
        )
