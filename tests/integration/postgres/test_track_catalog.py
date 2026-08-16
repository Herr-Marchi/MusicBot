from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from music_bot.adapters.outbound.postgres import PostgresTrackCatalog
from music_bot.application.ports.track_catalog import CatalogedTrack


def _unique_url() -> str:
    return f"https://example.com/{uuid.uuid4()}.mp3"


@pytest.mark.integration
class TestPostgresTrackCatalog:
    async def test_upsert_then_get_round_trips(
        self, postgres_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        catalog = PostgresTrackCatalog(session_factory=postgres_session_factory)
        url: str = _unique_url()

        written: CatalogedTrack = await catalog.upsert(
            url=url, title="Integration Song", duration_seconds=210
        )
        read: CatalogedTrack | None = await catalog.get(url=url)

        assert written == CatalogedTrack(url=url, title="Integration Song", duration_seconds=210)
        assert read == written

    async def test_upsert_twice_updates_instead_of_duplicating(
        self, postgres_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        catalog = PostgresTrackCatalog(session_factory=postgres_session_factory)
        url: str = _unique_url()

        await catalog.upsert(url=url, title="First Title", duration_seconds=100)
        await catalog.upsert(url=url, title="Second Title", duration_seconds=200)

        result: CatalogedTrack | None = await catalog.get(url=url)
        assert result is not None
        assert result.title == "Second Title"
        assert result.duration_seconds == 200

    async def test_get_missing_returns_none(
        self, postgres_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        catalog = PostgresTrackCatalog(session_factory=postgres_session_factory)

        assert await catalog.get(url=_unique_url()) is None
