from __future__ import annotations

from sqlalchemy import ScalarResult, Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import ReturningInsert

from music_bot.adapters.outbound.postgres.models import TrackModel
from music_bot.application.ports.track_catalog import CatalogedTrack


async def upsert_track_row(
    session: AsyncSession,
    *,
    url: str,
    title: str,
    duration_seconds: int,
) -> TrackModel:
    statement: ReturningInsert[tuple[TrackModel]] = (
        insert(TrackModel)
        .values(url=url, title=title, duration_seconds=duration_seconds)
        .on_conflict_do_update(
            index_elements=[TrackModel.url],
            set_={"title": title, "duration_seconds": duration_seconds},
        )
        .returning(TrackModel)
    )
    result: ScalarResult[TrackModel] = await session.scalars(statement)
    return result.one()


def track_row_to_cataloged(track: TrackModel) -> CatalogedTrack:
    return CatalogedTrack(
        url=track.url,
        title=track.title,
        duration_seconds=track.duration_seconds,
    )


class PostgresTrackCatalog:
    def __init__(self, *, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory: async_sessionmaker[AsyncSession] = session_factory

    async def get(self, *, url: str) -> CatalogedTrack | None:
        async with self._session_factory() as session:
            statement: Select[tuple[TrackModel]] = select(TrackModel).where(TrackModel.url == url)
            result: ScalarResult[TrackModel] = await session.scalars(statement)
            track: TrackModel | None = result.one_or_none()
            if track is None:
                return None

            return track_row_to_cataloged(track)

    async def upsert(
        self,
        *,
        url: str,
        title: str,
        duration_seconds: int,
    ) -> CatalogedTrack:
        async with self._session_factory() as session:
            track: TrackModel = await upsert_track_row(
                session,
                url=url,
                title=title,
                duration_seconds=duration_seconds,
            )
            await session.commit()
            return track_row_to_cataloged(track)
