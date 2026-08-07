from __future__ import annotations

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

from music_bot.adapters.outbound.postgres.models import (
    PlaylistModel,
    PlaylistTrackModel,
    TrackModel,
)
from music_bot.adapters.outbound.postgres.repositories.track_catalog import upsert_track_row
from music_bot.application.ports.playlists import (
    PlaylistData,
    PlaylistTrackData,
    PlaylistVisibility,
    TrackData,
)
from music_bot.domain.playlists.models import PlaylistAccess


class PostgresPlaylistRepository:
    def __init__(self, *, session: AsyncSession) -> None:
        self._session: AsyncSession = session

    async def get(self, *, playlist_id: str) -> PlaylistData | None:
        playlist: PlaylistModel | None = await self._session.get(
            PlaylistModel,
            UUID(playlist_id),
        )
        if playlist is None:
            return None

        return self._to_playlist_data(playlist)

    async def create(
        self,
        *,
        title: str,
        owner_id: int,
        access: PlaylistAccess,
    ) -> PlaylistData:
        playlist: PlaylistModel = PlaylistModel(
            title=title,
            owner_id=owner_id,
            access=access,
        )
        self._session.add(playlist)
        await self._session.flush()

        return self._to_playlist_data(playlist)

    async def set_title(self, *, playlist_id: str, title: str) -> None:
        statement: Update = (
            update(PlaylistModel).where(PlaylistModel.id == UUID(playlist_id)).values(title=title)
        )
        await self._session.execute(statement)

    async def set_access(self, *, playlist_id: str, access: PlaylistAccess) -> None:
        statement: Update = (
            update(PlaylistModel).where(PlaylistModel.id == UUID(playlist_id)).values(access=access)
        )
        await self._session.execute(statement)

    async def delete(self, *, playlist_id: str) -> None:
        statement: Delete = delete(PlaylistModel).where(PlaylistModel.id == UUID(playlist_id))
        await self._session.execute(statement)

    async def list(self, *, visibility: PlaylistVisibility) -> Sequence[PlaylistData]:
        clauses: Sequence[ColumnElement[bool]] = self._visibility_clauses(visibility)

        statement: Select[tuple[PlaylistModel]] = select(PlaylistModel)
        if clauses:
            statement = statement.where(or_(*clauses))

        result: ScalarResult[PlaylistModel] = await self._session.scalars(statement)
        return [self._to_playlist_data(playlist) for playlist in result.all()]

    async def get_tracks(self, *, playlist_id: str) -> Sequence[PlaylistTrackData]:
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

        return [self._to_playlist_track_data(playlist_track=row[0], track=row[1]) for row in rows]

    async def add_track(
        self,
        *,
        playlist_id: str,
        url: str,
        title: str,
        duration_seconds: int,
    ) -> PlaylistTrackData:
        track: TrackModel = await upsert_track_row(
            self._session,
            url=url,
            title=title,
            duration_seconds=duration_seconds,
        )

        next_position: Select[tuple[int]] = select(
            func.coalesce(func.max(PlaylistTrackModel.position) + 1, 0)
        ).where(PlaylistTrackModel.playlist_id == UUID(playlist_id))

        insert_statement: ReturningInsert[tuple[PlaylistTrackModel]] = (
            insert(PlaylistTrackModel)
            .values(
                playlist_id=UUID(playlist_id),
                track_id=track.id,
                position=next_position.scalar_subquery(),
            )
            .returning(PlaylistTrackModel)
        )
        insert_result: ScalarResult[PlaylistTrackModel] = await self._session.scalars(
            insert_statement
        )
        playlist_track: PlaylistTrackModel = insert_result.one()

        return self._to_playlist_track_data(
            playlist_track=playlist_track,
            track=track,
        )

    async def remove_track(self, *, playlist_track_id: str) -> None:
        playlist_track_uuid: UUID = UUID(playlist_track_id)
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
            return

        playlist_id, removed_position = deleted_row

        compress_positions_statement: Update = (
            update(PlaylistTrackModel)
            .where(
                PlaylistTrackModel.playlist_id == playlist_id,
                PlaylistTrackModel.position > removed_position,
            )
            .values(position=PlaylistTrackModel.position - 1)
        )
        await self._session.execute(compress_positions_statement)

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
    def _to_track_data(track: TrackModel) -> TrackData:
        return TrackData(
            id=str(track.id),
            url=track.url,
            title=track.title,
            duration_seconds=track.duration_seconds,
        )

    @classmethod
    def _to_playlist_track_data(
        cls,
        *,
        playlist_track: PlaylistTrackModel,
        track: TrackModel,
    ) -> PlaylistTrackData:
        return PlaylistTrackData(
            id=str(playlist_track.id),
            track=cls._to_track_data(track),
            position=playlist_track.position,
        )
