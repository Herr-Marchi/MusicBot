from __future__ import annotations

from music_bot.application.ports.track_catalog import CatalogedTrack, TrackCatalog
from music_bot.application.ports.track_source import TrackMetadata, TrackMetadataResolver


class CatalogBackedTrackMetadataResolver:
    def __init__(self, *, inner: TrackMetadataResolver, catalog: TrackCatalog) -> None:
        self._inner: TrackMetadataResolver = inner
        self._catalog: TrackCatalog = catalog

    async def resolve(self, *, source_url: str) -> TrackMetadata:
        cataloged: CatalogedTrack | None = await self._catalog.get(url=source_url)
        if cataloged is not None:
            return TrackMetadata(
                source_url=cataloged.url,
                title=cataloged.title,
                duration_seconds=cataloged.duration_seconds,
            )

        metadata: TrackMetadata = await self._inner.resolve(source_url=source_url)
        await self._catalog.upsert(
            url=metadata.source_url,
            title=metadata.title,
            duration_seconds=metadata.duration_seconds,
        )
        return metadata
