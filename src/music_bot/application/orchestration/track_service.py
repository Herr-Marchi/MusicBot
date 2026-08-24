from __future__ import annotations

import logging
from urllib.parse import urlsplit

from music_bot.application.ports.track import StoredTrack
from music_bot.application.ports.track_repository import TrackRepository
from music_bot.application.ports.track_source import TrackMetadata, TrackMetadataResolver

logger: logging.Logger = logging.getLogger(__name__)


class TrackService:
    def __init__(
        self,
        *,
        source: TrackMetadataResolver,
    ) -> None:
        self._source: TrackMetadataResolver = source

    async def get_or_register(
        self,
        *,
        url: str,
        repository: TrackRepository,
    ) -> StoredTrack:
        hostname: str | None = urlsplit(url).hostname
        logger.debug(
            "Track lookup started hostname=%r repository=%s",
            hostname,
            type(repository).__name__,
        )
        stored_track: StoredTrack | None = await repository.get_by_url(url=url)
        if stored_track is not None:
            logger.info(
                "Track catalog hit track_id=%s hostname=%r title=%r",
                stored_track.id,
                hostname,
                stored_track.title,
            )
            return stored_track

        logger.info("Track catalog miss hostname=%r; resolving metadata", hostname)
        metadata: TrackMetadata = await self._source.resolve_metadata(source_url=url)
        logger.debug(
            "Track metadata resolved hostname=%r title=%r duration_seconds=%s",
            urlsplit(metadata.url).hostname,
            metadata.title,
            metadata.duration_seconds,
        )
        saved: StoredTrack = await repository.save(
            url=metadata.url,
            title=metadata.title,
            duration_seconds=metadata.duration_seconds,
        )
        logger.info(
            "Track registered track_id=%s hostname=%r title=%r",
            saved.id,
            urlsplit(saved.url).hostname,
            saved.title,
        )
        return saved
