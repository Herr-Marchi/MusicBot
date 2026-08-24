from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from music_bot.adapters.outbound.postgres import PostgresUoWFactory
from music_bot.application.ports.track import StoredTrack


def _unique_url() -> str:
    return f"https://example.com/{uuid.uuid4()}.mp3"


@pytest.mark.integration
class TestPostgresTrackRepository:
    async def test_save_then_get_round_trips(
        self, postgres_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        uow_factory = PostgresUoWFactory(session_factory=postgres_session_factory)
        url = _unique_url()

        async with uow_factory() as uow:
            written = await uow.track_repository.save(
                url=url, title="Integration Song", duration_seconds=210
            )
            await uow.commit()
        async with uow_factory() as uow:
            read = await uow.track_repository.get_by_url(url=url)

        assert written == StoredTrack(
            id=written.id, url=url, title="Integration Song", duration_seconds=210
        )
        assert read == written

    async def test_save_updates_existing_track(
        self, postgres_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        uow_factory = PostgresUoWFactory(session_factory=postgres_session_factory)
        url = _unique_url()

        async with uow_factory() as uow:
            first = await uow.track_repository.save(
                url=url, title="First Title", duration_seconds=100
            )
            await uow.commit()
        async with uow_factory() as uow:
            second = await uow.track_repository.save(
                url=url, title="Second Title", duration_seconds=200
            )
            await uow.commit()

        assert second.id == first.id
        async with uow_factory() as uow:
            assert await uow.track_repository.get_by_url(url=url) == second

    async def test_get_missing_returns_none(
        self, postgres_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        uow_factory = PostgresUoWFactory(session_factory=postgres_session_factory)

        async with uow_factory() as uow:
            assert await uow.track_repository.get_by_url(url=_unique_url()) is None
