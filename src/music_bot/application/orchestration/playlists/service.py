from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from music_bot.application.contracts.errors import NotPlaylistOwnerError, PlaylistNotFoundError
from music_bot.application.ports.playlists import (
    PlaylistData,
    PlaylistTrackData,
    PlaylistUoW,
    PlaylistUoWFactory,
    PlaylistVisibility,
)
from music_bot.application.ports.track_source import TrackMetadata, TrackMetadataResolver
from music_bot.domain.playlists.models import PlaylistAccess


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaylistDetail:
    playlist: PlaylistData
    tracks: Sequence[PlaylistTrackData]


class PlaylistService:
    def __init__(
        self,
        *,
        uow_factory: PlaylistUoWFactory,
        metadata_resolver: TrackMetadataResolver,
    ) -> None:
        self._uow_factory: PlaylistUoWFactory = uow_factory
        self._metadata_resolver: TrackMetadataResolver = metadata_resolver

    async def create(
        self,
        *,
        owner_id: int,
        owner_username: str,
        title: str,
        access: PlaylistAccess,
    ) -> PlaylistData:
        async with self._uow_factory() as uow:
            await uow.user_repository.upsert(user_id=owner_id, username=owner_username)
            playlist: PlaylistData = await uow.playlist_repository.create(
                title=title,
                owner_id=owner_id,
                access=access,
            )
            await uow.commit()

        return playlist

    async def rename(self, *, playlist_id: str, requested_by: int, title: str) -> PlaylistData:
        async with self._uow_factory() as uow:
            playlist: PlaylistData = await self._require_updatable(
                uow, playlist_id=playlist_id, requested_by=requested_by
            )
            await uow.playlist_repository.set_title(playlist_id=playlist_id, title=title)
            await uow.commit()

        return PlaylistData(
            id=playlist.id,
            title=title,
            owner_id=playlist.owner_id,
            access=playlist.access,
        )

    async def set_access(
        self,
        *,
        playlist_id: str,
        requested_by: int,
        access: PlaylistAccess,
    ) -> PlaylistData:
        async with self._uow_factory() as uow:
            playlist: PlaylistData = await self._require_updatable(
                uow, playlist_id=playlist_id, requested_by=requested_by
            )
            await uow.playlist_repository.set_access(playlist_id=playlist_id, access=access)
            await uow.commit()

        return PlaylistData(
            id=playlist.id,
            title=playlist.title,
            owner_id=playlist.owner_id,
            access=access,
        )

    async def delete(self, *, playlist_id: str, requested_by: int) -> None:
        async with self._uow_factory() as uow:
            await self._require_updatable(uow, playlist_id=playlist_id, requested_by=requested_by)
            await uow.playlist_repository.delete(playlist_id=playlist_id)
            await uow.commit()

    async def list_editable(self, *, user_id: int) -> Sequence[PlaylistData]:
        async with self._uow_factory() as uow:
            return await uow.playlist_repository.list(
                visibility=PlaylistVisibility(owner_id=user_id)
            )

    async def list_readable(self, *, user_id: int) -> Sequence[PlaylistData]:
        async with self._uow_factory() as uow:
            return await uow.playlist_repository.list(
                visibility=PlaylistVisibility(owner_id=user_id, include_public=True)
            )

    async def get(self, *, playlist_id: str, requested_by: int) -> PlaylistDetail:
        async with self._uow_factory() as uow:
            playlist: PlaylistData = await self._require_readable(
                uow, playlist_id=playlist_id, requested_by=requested_by
            )
            tracks: Sequence[PlaylistTrackData] = await uow.playlist_repository.get_tracks(
                playlist_id=playlist_id
            )

        return PlaylistDetail(playlist=playlist, tracks=tracks)

    async def add_track(
        self,
        *,
        playlist_id: str,
        requested_by: int,
        url: str,
    ) -> PlaylistTrackData:
        async with self._uow_factory() as uow:
            await self._require_updatable(uow, playlist_id=playlist_id, requested_by=requested_by)
            metadata: TrackMetadata = await self._metadata_resolver.resolve(source_url=url)
            playlist_track: PlaylistTrackData = await uow.playlist_repository.add_track(
                playlist_id=playlist_id,
                url=metadata.source_url,
                title=metadata.title,
                duration_seconds=metadata.duration_seconds,
            )
            await uow.commit()

        return playlist_track

    async def remove_track(
        self,
        *,
        playlist_id: str,
        requested_by: int,
        position: int,
    ) -> None:
        async with self._uow_factory() as uow:
            await self._require_updatable(uow, playlist_id=playlist_id, requested_by=requested_by)
            tracks: Sequence[PlaylistTrackData] = await uow.playlist_repository.get_tracks(
                playlist_id=playlist_id
            )
            track: PlaylistTrackData | None = next(
                (t for t in tracks if t.position == position), None
            )
            if track is None:
                raise PlaylistNotFoundError()

            await uow.playlist_repository.remove_track(playlist_track_id=track.id)
            await uow.commit()

    @staticmethod
    async def _get_or_raise(uow: PlaylistUoW, *, playlist_id: str) -> PlaylistData:
        playlist: PlaylistData | None = await uow.playlist_repository.get(playlist_id=playlist_id)
        if playlist is None:
            raise PlaylistNotFoundError()

        return playlist

    @classmethod
    async def _require_updatable(
        cls,
        uow: PlaylistUoW,
        *,
        playlist_id: str,
        requested_by: int,
    ) -> PlaylistData:
        # Owner-only for now
        playlist: PlaylistData = await cls._get_or_raise(uow, playlist_id=playlist_id)
        if playlist.owner_id == requested_by:
            return playlist
        if playlist.access == PlaylistAccess.PUBLIC:
            raise NotPlaylistOwnerError()

        raise PlaylistNotFoundError()

    @classmethod
    async def _require_readable(
        cls,
        uow: PlaylistUoW,
        *,
        playlist_id: str,
        requested_by: int,
    ) -> PlaylistData:
        playlist: PlaylistData = await cls._get_or_raise(uow, playlist_id=playlist_id)
        if playlist.access != PlaylistAccess.PUBLIC and playlist.owner_id != requested_by:
            raise PlaylistNotFoundError()

        return playlist
