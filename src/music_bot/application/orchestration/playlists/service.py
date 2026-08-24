from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from music_bot.application.contracts.errors import NotPlaylistOwnerError, PlaylistNotFoundError
from music_bot.application.orchestration.track_service import TrackService
from music_bot.application.ports.playlists import (
    PlaylistData,
    PlaylistEntry,
    PlaylistVisibility,
)
from music_bot.application.ports.track import StoredTrack
from music_bot.application.ports.uow import UoW, UoWFactory
from music_bot.domain.playlists.models import PlaylistAccess

logger: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaylistDetail:
    playlist: PlaylistData
    tracks: Sequence[PlaylistEntry]


class PlaylistService:
    def __init__(
        self,
        *,
        uow_factory: UoWFactory,
        track_service: TrackService,
    ) -> None:
        self._uow_factory: UoWFactory = uow_factory
        self._track_service: TrackService = track_service

    async def create(
        self,
        *,
        owner_id: int,
        owner_username: str,
        title: str,
        access: PlaylistAccess,
    ) -> PlaylistData:
        logger.info(
            "Playlist create started owner_id=%s title=%r access=%s",
            owner_id,
            title,
            access.value,
        )
        async with self._uow_factory() as uow:
            await uow.user_repository.upsert(user_id=owner_id, username=owner_username)
            playlist: PlaylistData = await uow.playlist_repository.create(
                title=title,
                owner_id=owner_id,
                access=access,
            )
            await uow.commit()

        logger.info(
            "Playlist create completed playlist_id=%s owner_id=%s title=%r",
            playlist.id,
            owner_id,
            playlist.title,
        )
        return playlist

    async def rename(self, *, playlist_id: str, requested_by: int, title: str) -> PlaylistData:
        logger.info(
            "Playlist rename started playlist_id=%s requested_by=%s title=%r",
            playlist_id,
            requested_by,
            title,
        )
        async with self._uow_factory() as uow:
            playlist: PlaylistData = await self._require_updatable(
                uow, playlist_id=playlist_id, requested_by=requested_by
            )
            await uow.playlist_repository.set_title(playlist_id=playlist_id, title=title)
            await uow.commit()

        renamed = PlaylistData(
            id=playlist.id,
            title=title,
            owner_id=playlist.owner_id,
            access=playlist.access,
        )
        logger.info(
            "Playlist rename completed playlist_id=%s requested_by=%s title=%r",
            playlist_id,
            requested_by,
            title,
        )
        return renamed

    async def set_access(
        self,
        *,
        playlist_id: str,
        requested_by: int,
        access: PlaylistAccess,
    ) -> PlaylistData:
        logger.info(
            "Playlist access update started playlist_id=%s requested_by=%s access=%s",
            playlist_id,
            requested_by,
            access.value,
        )
        async with self._uow_factory() as uow:
            playlist: PlaylistData = await self._require_updatable(
                uow, playlist_id=playlist_id, requested_by=requested_by
            )
            await uow.playlist_repository.set_access(playlist_id=playlist_id, access=access)
            await uow.commit()

        updated = PlaylistData(
            id=playlist.id,
            title=playlist.title,
            owner_id=playlist.owner_id,
            access=access,
        )
        logger.info(
            "Playlist access update completed playlist_id=%s requested_by=%s access=%s",
            playlist_id,
            requested_by,
            access.value,
        )
        return updated

    async def delete(self, *, playlist_id: str, requested_by: int) -> None:
        logger.info(
            "Playlist delete started playlist_id=%s requested_by=%s",
            playlist_id,
            requested_by,
        )
        async with self._uow_factory() as uow:
            await self._require_updatable(uow, playlist_id=playlist_id, requested_by=requested_by)
            await uow.playlist_repository.delete(playlist_id=playlist_id)
            await uow.commit()
        logger.info(
            "Playlist delete completed playlist_id=%s requested_by=%s",
            playlist_id,
            requested_by,
        )

    async def list_editable(self, *, user_id: int) -> Sequence[PlaylistData]:
        logger.debug("Editable playlist list started user_id=%s", user_id)
        async with self._uow_factory() as uow:
            playlists: Sequence[PlaylistData] = await uow.playlist_repository.list(
                visibility=PlaylistVisibility(owner_id=user_id)
            )
        logger.debug(
            "Editable playlist list completed user_id=%s count=%s", user_id, len(playlists)
        )
        return playlists

    async def list_readable(self, *, user_id: int) -> Sequence[PlaylistData]:
        logger.debug("Readable playlist list started user_id=%s", user_id)
        async with self._uow_factory() as uow:
            playlists: Sequence[PlaylistData] = await uow.playlist_repository.list(
                visibility=PlaylistVisibility(owner_id=user_id, include_public=True)
            )
        logger.debug(
            "Readable playlist list completed user_id=%s count=%s", user_id, len(playlists)
        )
        return playlists

    async def get(self, *, playlist_id: str, requested_by: int) -> PlaylistDetail:
        logger.debug(
            "Playlist read started playlist_id=%s requested_by=%s",
            playlist_id,
            requested_by,
        )
        async with self._uow_factory() as uow:
            playlist: PlaylistData = await self._require_readable(
                uow, playlist_id=playlist_id, requested_by=requested_by
            )
            tracks: Sequence[PlaylistEntry] = await uow.playlist_repository.get_tracks(
                playlist_id=playlist_id
            )

        detail = PlaylistDetail(playlist=playlist, tracks=tracks)
        logger.info(
            "Playlist read completed playlist_id=%s requested_by=%s track_count=%s",
            playlist_id,
            requested_by,
            len(tracks),
        )
        return detail

    async def add_track(
        self,
        *,
        playlist_id: str,
        requested_by: int,
        url: str,
    ) -> PlaylistEntry:
        logger.info(
            "Playlist add track started playlist_id=%s requested_by=%s",
            playlist_id,
            requested_by,
        )
        async with self._uow_factory() as uow:
            await self._require_updatable(uow, playlist_id=playlist_id, requested_by=requested_by)
            stored_track: StoredTrack = await self._track_service.get_or_register(
                url=url,
                repository=uow.track_repository,
            )
            playlist_entry: PlaylistEntry = await uow.playlist_repository.add_track(
                playlist_id=playlist_id,
                track=stored_track,
            )
            await uow.commit()

        logger.info(
            "Playlist add track completed playlist_id=%s requested_by=%s entry_id=%s "
            "track_id=%s position=%s",
            playlist_id,
            requested_by,
            playlist_entry.id,
            playlist_entry.track.id,
            playlist_entry.position,
        )
        return playlist_entry

    async def remove_track(
        self,
        *,
        playlist_id: str,
        requested_by: int,
        position: int,
    ) -> None:
        logger.info(
            "Playlist remove track started playlist_id=%s requested_by=%s position=%s",
            playlist_id,
            requested_by,
            position,
        )
        async with self._uow_factory() as uow:
            await self._require_updatable(uow, playlist_id=playlist_id, requested_by=requested_by)
            tracks: Sequence[PlaylistEntry] = await uow.playlist_repository.get_tracks(
                playlist_id=playlist_id
            )
            entry: PlaylistEntry | None = next((t for t in tracks if t.position == position), None)
            if entry is None:
                logger.info(
                    "Playlist remove track rejected missing position playlist_id=%s position=%s",
                    playlist_id,
                    position,
                )
                raise PlaylistNotFoundError()

            await uow.playlist_repository.remove_track(entry_id=entry.id)
            await uow.commit()
        logger.info(
            "Playlist remove track completed playlist_id=%s requested_by=%s entry_id=%s "
            "position=%s",
            playlist_id,
            requested_by,
            entry.id,
            position,
        )

    @staticmethod
    async def _get_or_raise(uow: UoW, *, playlist_id: str) -> PlaylistData:
        logger.debug("Playlist repository lookup playlist_id=%s", playlist_id)
        playlist: PlaylistData | None = await uow.playlist_repository.get(playlist_id=playlist_id)
        if playlist is None:
            logger.info("Playlist lookup returned not found playlist_id=%s", playlist_id)
            raise PlaylistNotFoundError()

        logger.debug(
            "Playlist lookup returned playlist_id=%s owner_id=%s access=%s",
            playlist.id,
            playlist.owner_id,
            playlist.access.value,
        )
        return playlist

    @classmethod
    async def _require_updatable(
        cls,
        uow: UoW,
        *,
        playlist_id: str,
        requested_by: int,
    ) -> PlaylistData:
        # Owner-only for now
        playlist: PlaylistData = await cls._get_or_raise(uow, playlist_id=playlist_id)
        if playlist.owner_id == requested_by:
            logger.debug(
                "Playlist update authorization passed playlist_id=%s requested_by=%s",
                playlist_id,
                requested_by,
            )
            return playlist
        if playlist.access == PlaylistAccess.PUBLIC:
            logger.info(
                "Playlist update authorization rejected not owner playlist_id=%s requested_by=%s",
                playlist_id,
                requested_by,
            )
            raise NotPlaylistOwnerError()

        logger.info(
            "Playlist update authorization hidden as not found playlist_id=%s requested_by=%s",
            playlist_id,
            requested_by,
        )
        raise PlaylistNotFoundError()

    @classmethod
    async def _require_readable(
        cls,
        uow: UoW,
        *,
        playlist_id: str,
        requested_by: int,
    ) -> PlaylistData:
        playlist: PlaylistData = await cls._get_or_raise(uow, playlist_id=playlist_id)
        if playlist.access != PlaylistAccess.PUBLIC and playlist.owner_id != requested_by:
            logger.info(
                "Playlist read authorization rejected playlist_id=%s requested_by=%s",
                playlist_id,
                requested_by,
            )
            raise PlaylistNotFoundError()

        logger.debug(
            "Playlist read authorization passed playlist_id=%s requested_by=%s",
            playlist_id,
            requested_by,
        )
        return playlist
