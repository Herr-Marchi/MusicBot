from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import ScalarResult
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from music_bot.adapters.outbound.postgres.models import TrackModel
from music_bot.adapters.outbound.postgres.repositories import PostgresTrackRepository
from music_bot.application.ports.track import StoredTrack


def _track_model(*, url: str, title: str, duration_seconds: int) -> TrackModel:
    track = TrackModel(
        url=url,
        title=title,
        duration_seconds=duration_seconds,
    )
    track.id = uuid4()
    return track


@pytest.mark.unit
class TestInjectedPostgresTrackRepository:
    async def test_get_by_url_maps_model_from_injected_session(self) -> None:
        model = _track_model(
            url="https://example.com/track",
            title="Track",
            duration_seconds=10,
        )
        scalar_result = MagicMock(spec=ScalarResult)
        scalar_result.one_or_none.return_value = model
        session = MagicMock(spec=AsyncSession)
        session.scalars = AsyncMock(return_value=scalar_result)

        track = await PostgresTrackRepository(session=session).get_by_url(url=model.url)

        assert track == StoredTrack(
            id=str(model.id),
            url=model.url,
            title=model.title,
            duration_seconds=model.duration_seconds,
        )
        session.scalars.assert_awaited_once()

    async def test_get_by_url_returns_none_for_missing_row(self) -> None:
        scalar_result = MagicMock(spec=ScalarResult)
        scalar_result.one_or_none.return_value = None
        session = MagicMock(spec=AsyncSession)
        session.scalars = AsyncMock(return_value=scalar_result)

        track = await PostgresTrackRepository(session=session).get_by_url(
            url="https://example.com/missing"
        )

        assert track is None

    async def test_save_keeps_upsert_inside_track_repository(self) -> None:
        model = _track_model(
            url="https://example.com/track",
            title="Updated",
            duration_seconds=20,
        )
        scalar_result = MagicMock(spec=ScalarResult)
        scalar_result.one.return_value = model
        session = MagicMock(spec=AsyncSession)
        session.scalars = AsyncMock(return_value=scalar_result)

        track = await PostgresTrackRepository(session=session).save(
            url=model.url,
            title=model.title,
            duration_seconds=model.duration_seconds,
        )

        statement = session.scalars.await_args.args[0]
        sql = str(statement.compile(dialect=postgresql.dialect()))
        assert "ON CONFLICT (url) DO UPDATE" in sql
        assert "RETURNING tracks" in sql
        assert track.id == str(model.id)
