from __future__ import annotations

import logging
from collections.abc import Sequence
from urllib.parse import urlsplit

from music_bot.application.ports.track_source import (
    TrackMetadata,
    TrackNotOwnedError,
    TrackSource,
    TrackSourceError,
)

logger: logging.Logger = logging.getLogger(__name__)


class TrackSourceRouter(TrackSource):
    def __init__(self, *, sources: Sequence[TrackSource]) -> None:
        self._sources: tuple[TrackSource, ...] = tuple(sources)
        logger.debug(
            "Track source router created sources=%s",
            ",".join(type(source).__name__ for source in self._sources) or "<empty>",
        )

    async def validate_url(self, *, source_url: str) -> TrackSource:
        hostname: str | None = urlsplit(source_url).hostname
        logger.debug(
            "Track source routing started hostname=%r candidates=%s",
            hostname,
            len(self._sources),
        )
        for index, source in enumerate(self._sources, start=1):
            source_name: str = type(source).__name__
            logger.debug(
                "Track source candidate checking hostname=%r candidate=%s position=%s/%s",
                hostname,
                source_name,
                index,
                len(self._sources),
            )
            try:
                selected: TrackSource = await source.validate_url(source_url=source_url)
            except TrackNotOwnedError:
                logger.debug(
                    "Track source candidate declined hostname=%r candidate=%s",
                    hostname,
                    source_name,
                )
                continue
            except TrackSourceError as exc:
                logger.warning(
                    "Track source candidate rejected URL hostname=%r candidate=%s reason=%s",
                    hostname,
                    source_name,
                    exc,
                )
                raise
            except Exception:
                logger.exception(
                    "Track source candidate validation failed hostname=%r candidate=%s",
                    hostname,
                    source_name,
                )
                raise

            logger.info(
                "Track source selected hostname=%r candidate=%s resolver=%s",
                hostname,
                source_name,
                type(selected).__name__,
            )
            return selected

        logger.info("Track source routing rejected unsupported hostname=%r", hostname)
        raise TrackNotOwnedError("That URL isn't from a supported source.")

    async def _resolve_metadata(self, *, source_url: str) -> TrackMetadata:
        logger.debug("Nested router metadata resolution hostname=%r", urlsplit(source_url).hostname)
        source: TrackSource = await self.validate_url(source_url=source_url)
        return await source._resolve_metadata(source_url=source_url)

    async def _resolve_stream(self, *, source_url: str) -> str:
        logger.debug("Nested router stream resolution hostname=%r", urlsplit(source_url).hostname)
        source: TrackSource = await self.validate_url(source_url=source_url)
        return await source._resolve_stream(source_url=source_url)
