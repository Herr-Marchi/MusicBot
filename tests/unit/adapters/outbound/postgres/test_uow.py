from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from music_bot.adapters.outbound.postgres.repositories import (
    PostgresPlaylistRepository,
    PostgresTrackRepository,
    PostgresUserRepository,
)
from music_bot.adapters.outbound.postgres.uow import PostgresUoW, PostgresUoWFactory


def _session() -> MagicMock:
    session = MagicMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.mark.unit
class TestPostgresUoW:
    async def test_commit_uses_injected_session(self) -> None:
        session = _session()
        uow = PostgresUoW(
            session=session,
            user_repository=MagicMock(spec=PostgresUserRepository),
            playlist_repository=MagicMock(spec=PostgresPlaylistRepository),
            track_repository=MagicMock(spec=PostgresTrackRepository),
        )

        await uow.commit()

        session.commit.assert_awaited_once_with()

    async def test_context_rolls_back_and_closes_same_session(self) -> None:
        session = _session()
        uow = PostgresUoW(
            session=session,
            user_repository=MagicMock(spec=PostgresUserRepository),
            playlist_repository=MagicMock(spec=PostgresPlaylistRepository),
            track_repository=MagicMock(spec=PostgresTrackRepository),
        )

        async with uow:
            pass

        session.rollback.assert_awaited_once_with()
        session.close.assert_awaited_once_with()


@pytest.mark.unit
class TestPostgresUoWFactory:
    def test_injects_one_session_into_every_repository(self) -> None:
        session = _session()
        session_factory = MagicMock(spec=async_sessionmaker)
        session_factory.return_value = session

        uow = PostgresUoWFactory(session_factory=session_factory)()

        assert uow._session is session
        assert uow.user_repository._session is session
        assert uow.playlist_repository._session is session
        assert uow.track_repository._session is session
        session_factory.assert_called_once_with()
