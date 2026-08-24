from __future__ import annotations

import logging
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Delete,
    Result,
    Row,
    ScalarResult,
    Select,
    Update,
    delete,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.dml import ReturningDelete, ReturningInsert

from music_bot.adapters.outbound.postgres.mappers import to_stored_track
from music_bot.adapters.outbound.postgres.models import (
    PlaylistModel,
    PlaylistTrackModel,
    TrackModel,
)
from music_bot.application.ports.playlists import (
    PlaylistData,
    PlaylistEntry,
    PlaylistVisibility,
)
from music_bot.application.ports.track import StoredTrack
from music_bot.domain.playlists.models import PlaylistAccess

logger: logging.Logger = logging.getLogger(__name__)


class PostgresPlaylistRepository:
    """Owns playlists and playlist-track links; it never writes tracks."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session: AsyncSession = session

    async def get(self, *, playlist_id: str) -> PlaylistData | None:
        logger.debug("Postgres playlist lookup started playlist_id=%s", playlist_id)
        playlist: PlaylistModel | None = await self._session.get(
            PlaylistModel,
            UUID(playlist_id),
        )
        if playlist is None:
            logger.debug(
                "Postgres playlist lookup completed playlist_id=%s found=False", playlist_id
            )
            return None

        data: PlaylistData = self._to_playlist_data(playlist)
        logger.debug(
            "Postgres playlist lookup completed playlist_id=%s found=True owner_id=%s access=%s",
            playlist_id,
            data.owner_id,
            data.access.value,
        )
        return data

    async def create(
        self,
        *,
        title: str,
        owner_id: int,
        access: PlaylistAccess,
    ) -> PlaylistData:
        logger.debug(
            "Postgres playlist insert started owner_id=%s title=%r access=%s",
            owner_id,
            title,
            access.value,
        )
        playlist: PlaylistModel = PlaylistModel(
            title=title,
            owner_id=owner_id,
            access=access,
        )
        self._session.add(playlist)
        await self._session.flush()

        data: PlaylistData = self._to_playlist_data(playlist)
        logger.info(
            "Postgres playlist insert completed playlist_id=%s owner_id=%s title=%r",
            data.id,
            owner_id,
            data.title,
        )
        return data

    async def set_title(self, *, playlist_id: str, title: str) -> None:
        logger.debug(
            "Postgres playlist title update started playlist_id=%s title=%r",
            playlist_id,
            title,
        )
        statement: Update = (
            update(PlaylistModel).where(PlaylistModel.id == UUID(playlist_id)).values(title=title)
        )
        await self._session.execute(statement)
        logger.debug("Postgres playlist title update completed playlist_id=%s", playlist_id)

    async def set_access(self, *, playlist_id: str, access: PlaylistAccess) -> None:
        logger.debug(
            "Postgres playlist access update started playlist_id=%s access=%s",
            playlist_id,
            access.value,
        )
        statement: Update = (
            update(PlaylistModel).where(PlaylistModel.id == UUID(playlist_id)).values(access=access)
        )
        await self._session.execute(statement)
        logger.debug("Postgres playlist access update completed playlist_id=%s", playlist_id)

    async def delete(self, *, playlist_id: str) -> None:
        logger.debug("Postgres playlist delete started playlist_id=%s", playlist_id)
        statement: Delete = delete(PlaylistModel).where(PlaylistModel.id == UUID(playlist_id))
        await self._session.execute(statement)
        logger.info("Postgres playlist delete completed playlist_id=%s", playlist_id)

    async def list(self, *, visibility: PlaylistVisibility) -> Sequence[PlaylistData]:
        logger.debug(
            "Postgres playlist list started owner_id=%s include_public=%s",
            visibility.owner_id,
            visibility.include_public,
        )
        clauses: Sequence[ColumnElement[bool]] = self._visibility_clauses(visibility)

        statement: Select[tuple[PlaylistModel]] = select(PlaylistModel)
        if clauses:
            statement = statement.where(or_(*clauses))

        result: ScalarResult[PlaylistModel] = await self._session.scalars(statement)
        playlists: list[PlaylistData] = [
            self._to_playlist_data(playlist) for playlist in result.all()
        ]
        logger.debug(
            "Postgres playlist list completed owner_id=%s include_public=%s count=%s",
            visibility.owner_id,
            visibility.include_public,
            len(playlists),
        )
        return playlists

    async def get_tracks(self, *, playlist_id: str) -> Sequence[PlaylistEntry]:
        logger.debug("Postgres playlist tracks lookup started playlist_id=%s", playlist_id)
        statement: Select[tuple[PlaylistTrackModel, TrackModel]] = (
            select(PlaylistTrackModel, TrackModel)
            .join(TrackModel, TrackModel.id == PlaylistTrackModel.track_id)
            .where(PlaylistTrackModel.playlist_id == UUID(playlist_id))
            .order_by(PlaylistTrackModel.position)
        )
        result: Result[tuple[PlaylistTrackModel, TrackModel]] = await self._session.execute(
            statement
        )
        rows: Sequence[Row[tuple[PlaylistTrackModel, TrackModel]]] = result.all()

        entries: list[PlaylistEntry] = [
            self._to_playlist_entry(playlist_track=row[0], track=row[1]) for row in rows
        ]
        logger.debug(
            "Postgres playlist tracks lookup completed playlist_id=%s count=%s",
            playlist_id,
            len(entries),
        )
        return entries

    async def add_track(self, *, playlist_id: str, track: StoredTrack) -> PlaylistEntry:
        logger.debug(
            "Postgres playlist track insert started playlist_id=%s track_id=%s",
            playlist_id,
            track.id,
        )
        next_position: Select[tuple[int]] = select(
            func.coalesce(func.max(PlaylistTrackModel.position) + 1, 0)
        ).where(PlaylistTrackModel.playlist_id == UUID(playlist_id))

        insert_statement: ReturningInsert[tuple[PlaylistTrackModel]] = (
            insert(PlaylistTrackModel)
            .values(
                playlist_id=UUID(playlist_id),
                track_id=UUID(track.id),
                position=next_position.scalar_subquery(),
            )
            .returning(PlaylistTrackModel)
        )
        insert_result: ScalarResult[PlaylistTrackModel] = await self._session.scalars(
            insert_statement
        )
        playlist_track: PlaylistTrackModel = insert_result.one()

        entry = PlaylistEntry(
            id=str(playlist_track.id),
            track=track,
            position=playlist_track.position,
        )
        logger.info(
            "Postgres playlist track insert completed playlist_id=%s entry_id=%s "
            "track_id=%s position=%s",
            playlist_id,
            entry.id,
            track.id,
            entry.position,
        )
        return entry

    async def remove_track(self, *, entry_id: str) -> None:
        logger.debug("Postgres playlist track delete started entry_id=%s", entry_id)
        playlist_track_uuid: UUID = UUID(entry_id)
        delete_playlist_track_statement: ReturningDelete[tuple[UUID, int]] = (
            delete(PlaylistTrackModel)
            .where(PlaylistTrackModel.id == playlist_track_uuid)
            .returning(PlaylistTrackModel.playlist_id, PlaylistTrackModel.position)
        )
        delete_result: Result[tuple[UUID, int]] = await self._session.execute(
            delete_playlist_track_statement
        )
        deleted_row: Row[tuple[UUID, int]] | None = delete_result.one_or_none()
        if deleted_row is None:
            logger.debug(
                "Postgres playlist track delete completed entry_id=%s found=False", entry_id
            )
            return

        playlist_id: UUID = deleted_row[0]
        removed_position: int = deleted_row[1]

        compress_positions_statement: Update = (
            update(PlaylistTrackModel)
            .where(
                PlaylistTrackModel.playlist_id == playlist_id,
                PlaylistTrackModel.position > removed_position,
            )
            .values(position=PlaylistTrackModel.position - 1)
        )
        await self._session.execute(compress_positions_statement)
        logger.info(
            "Postgres playlist track delete completed entry_id=%s playlist_id=%s "
            "removed_position=%s positions_compressed=True",
            entry_id,
            playlist_id,
            removed_position,
        )

    @staticmethod
    def _visibility_clauses(visibility: PlaylistVisibility) -> Sequence[ColumnElement[bool]]:
        clauses: list[ColumnElement[bool]] = []
        if visibility.owner_id is not None:
            clauses.append(PlaylistModel.owner_id == visibility.owner_id)
        if visibility.include_public:
            clauses.append(PlaylistModel.access == PlaylistAccess.PUBLIC)

        return clauses

    @staticmethod
    def _to_playlist_data(playlist: PlaylistModel) -> PlaylistData:
        return PlaylistData(
            id=str(playlist.id),
            title=playlist.title,
            owner_id=playlist.owner_id,
            access=playlist.access,
        )

    @staticmethod
    def _to_playlist_entry(
        *,
        playlist_track: PlaylistTrackModel,
        track: TrackModel,
    ) -> PlaylistEntry:
        return PlaylistEntry(
            id=str(playlist_track.id),
            track=to_stored_track(track),
            position=playlist_track.position,
        )
