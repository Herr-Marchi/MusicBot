from __future__ import annotations

import logging
from urllib.parse import urlsplit

from sqlalchemy import ScalarResult, Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.dml import ReturningInsert

from music_bot.adapters.outbound.postgres.mappers import to_stored_track
from music_bot.adapters.outbound.postgres.models import TrackModel
from music_bot.application.ports.track import StoredTrack

logger: logging.Logger = logging.getLogger(__name__)


class PostgresTrackRepository:
    """The only writer and direct lookup owner for the tracks table."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session: AsyncSession = session

    async def get_by_url(self, *, url: str) -> StoredTrack | None:
        hostname: str | None = urlsplit(url).hostname
        logger.debug("Postgres track lookup started hostname=%r", hostname)
        statement: Select[tuple[TrackModel]] = select(TrackModel).where(TrackModel.url == url)
        result: ScalarResult[TrackModel] = await self._session.scalars(statement)
        track: TrackModel | None = result.one_or_none()
        stored_track: StoredTrack | None = to_stored_track(track) if track is not None else None
        logger.debug(
            "Postgres track lookup completed hostname=%r found=%s track_id=%s",
            hostname,
            stored_track is not None,
            stored_track.id if stored_track is not None else None,
        )
        return stored_track

    async def save(
        self,
        *,
        url: str,
        title: str,
        duration_seconds: int,
    ) -> StoredTrack:
        hostname: str | None = urlsplit(url).hostname
        logger.debug(
            "Postgres track upsert started hostname=%r title=%r duration_seconds=%s",
            hostname,
            title,
            duration_seconds,
        )
        statement: ReturningInsert[tuple[TrackModel]] = (
            insert(TrackModel)
            .values(url=url, title=title, duration_seconds=duration_seconds)
            .on_conflict_do_update(
                index_elements=[TrackModel.url],
                set_={"title": title, "duration_seconds": duration_seconds},
            )
            .returning(TrackModel)
        )
        result: ScalarResult[TrackModel] = await self._session.scalars(statement)
        stored_track: StoredTrack = to_stored_track(result.one())
        logger.info(
            "Postgres track upsert completed track_id=%s hostname=%r title=%r",
            stored_track.id,
            hostname,
            stored_track.title,
        )
        return stored_track
