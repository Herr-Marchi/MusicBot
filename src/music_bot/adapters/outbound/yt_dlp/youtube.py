from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, ClassVar, cast
from urllib.parse import urlsplit

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from music_bot.adapters.outbound.url_safety import UnsafeUrlError, ensure_safe_url
from music_bot.application.ports.track_source import (
    TrackMetadata,
    TrackNotOwnedError,
    TrackSource,
    TrackSourceError,
)

if TYPE_CHECKING:
    from yt_dlp import _Params as YtDlpOptions

logger: logging.Logger = logging.getLogger(__name__)

_SOCKET_TIMEOUT_SECONDS: int = 15

type YtDlpInfo = Mapping[str, object]


class YtDlpTrackSource(TrackSource):
    SOURCE_HOSTS: ClassVar[frozenset[str]] = frozenset(
        {
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "youtu.be",
        }
    )
    STREAM_HOST_SUFFIXES: ClassVar[frozenset[str]] = frozenset(
        {"googlevideo.com", "youtube.com", "youtu.be"}
    )

    async def validate_url(self, *, source_url: str) -> TrackSource:
        hostname: str | None = urlsplit(source_url).hostname
        normalized_hostname: str = hostname.rstrip(".").lower() if hostname else ""
        logger.debug(
            "yt-dlp source ownership check hostname=%r normalized_hostname=%r",
            hostname,
            normalized_hostname,
        )
        if not normalized_hostname or normalized_hostname not in self.SOURCE_HOSTS:
            logger.debug("yt-dlp source declined hostname=%r", hostname)
            raise TrackNotOwnedError("That URL isn't from a supported source.")

        logger.debug("yt-dlp source accepted ownership hostname=%r", hostname)
        try:
            logger.debug("yt-dlp input URL safety check hostname=%r", hostname)
            await ensure_safe_url(source_url)
        except UnsafeUrlError as exc:
            logger.warning("yt-dlp input URL rejected hostname=%r reason=%s", hostname, exc)
            raise TrackSourceError(str(exc)) from exc
        logger.debug("yt-dlp input URL accepted hostname=%r", hostname)
        return self

    async def _resolve_metadata(self, *, source_url: str) -> TrackMetadata:
        source_hostname: str | None = urlsplit(source_url).hostname
        logger.info("yt-dlp metadata resolution started hostname=%r", source_hostname)
        options: YtDlpOptions = {
            "noplaylist": True,
            "quiet": True,
            "socket_timeout": _SOCKET_TIMEOUT_SECONDS,
        }
        info: YtDlpInfo = await asyncio.to_thread(
            self._extract_info,
            source_url,
            options,
        )

        raw_canonical_url: object = info.get("webpage_url")
        canonical_url: str = (
            raw_canonical_url
            if isinstance(raw_canonical_url, str) and raw_canonical_url
            else source_url
        )
        raw_title: object = info.get("title")
        title: str = raw_title if isinstance(raw_title, str) and raw_title else canonical_url
        raw_duration: object = info.get("duration")
        duration_seconds: int = (
            max(0, int(raw_duration))
            if isinstance(raw_duration, int | float) and not isinstance(raw_duration, bool)
            else 0
        )
        canonical_hostname: str | None = urlsplit(canonical_url).hostname
        logger.debug(
            "yt-dlp metadata extracted source_hostname=%r canonical_hostname=%r "
            "title=%r duration_seconds=%s",
            source_hostname,
            canonical_hostname,
            title,
            duration_seconds,
        )
        await self.validate_url(source_url=canonical_url)
        metadata = TrackMetadata(
            url=canonical_url,
            title=title,
            duration_seconds=duration_seconds,
        )
        logger.info(
            "yt-dlp metadata resolution completed hostname=%r title=%r duration_seconds=%s",
            canonical_hostname,
            title,
            duration_seconds,
        )
        return metadata

    async def _resolve_stream(self, *, source_url: str) -> str:
        source_hostname: str | None = urlsplit(source_url).hostname
        logger.info("yt-dlp stream resolution started hostname=%r", source_hostname)
        options: YtDlpOptions = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "quiet": True,
            "socket_timeout": _SOCKET_TIMEOUT_SECONDS,
        }
        info: YtDlpInfo = await asyncio.to_thread(
            self._extract_info,
            source_url,
            options,
        )
        stream_url: object = info.get("url")
        if not isinstance(stream_url, str) or not stream_url:
            logger.warning("yt-dlp returned no stream URL hostname=%r", source_hostname)
            raise TrackSourceError("Could not resolve a playable audio URL.")
        stream_hostname: str | None = urlsplit(stream_url).hostname
        logger.debug(
            "yt-dlp stream URL extracted source_hostname=%r stream_hostname=%r",
            source_hostname,
            stream_hostname,
        )
        await self._validate_stream_url(stream_url=stream_url)
        logger.info(
            "yt-dlp stream resolution completed source_hostname=%r stream_hostname=%r",
            source_hostname,
            stream_hostname,
        )
        return stream_url

    async def _validate_stream_url(self, *, stream_url: str) -> None:
        hostname: str | None = urlsplit(stream_url).hostname
        normalized_hostname: str = hostname.rstrip(".").lower() if hostname else ""
        host_allowed: bool = any(
            normalized_hostname == suffix or normalized_hostname.endswith(f".{suffix}")
            for suffix in self.STREAM_HOST_SUFFIXES
        )
        logger.debug(
            "yt-dlp stream host allowlist check hostname=%r normalized_hostname=%r accepted=%s",
            hostname,
            normalized_hostname,
            host_allowed,
        )
        if not host_allowed:
            logger.warning("yt-dlp stream host rejected hostname=%r", hostname)
            raise TrackSourceError("The resolved stream URL is not supported.")

        try:
            logger.debug("yt-dlp stream URL safety check hostname=%r", hostname)
            await ensure_safe_url(stream_url)
        except UnsafeUrlError as exc:
            logger.warning("yt-dlp stream URL rejected hostname=%r reason=%s", hostname, exc)
            raise TrackSourceError(str(exc)) from exc
        logger.debug("yt-dlp stream URL accepted hostname=%r", hostname)

    @staticmethod
    def _extract_info(source_url: str, options: YtDlpOptions) -> YtDlpInfo:
        hostname: str | None = urlsplit(source_url).hostname
        operation: str = "stream" if "format" in options else "metadata"
        logger.debug(
            "yt-dlp extract_info call started operation=%s hostname=%r timeout_seconds=%s",
            operation,
            hostname,
            options.get("socket_timeout"),
        )
        try:
            with YoutubeDL(options) as youtube_dl:
                raw_info: object = youtube_dl.extract_info(source_url, download=False)
        except DownloadError as exc:
            logger.warning(
                "yt-dlp extract_info failed operation=%s hostname=%r error_type=%s",
                operation,
                hostname,
                type(exc).__name__,
            )
            raise TrackSourceError("Could not resolve that track.") from exc

        if not isinstance(raw_info, Mapping):
            logger.warning(
                "yt-dlp extract_info returned unexpected type operation=%s hostname=%r type=%s",
                operation,
                hostname,
                type(raw_info).__name__,
            )
            raise TrackSourceError("The track source returned no metadata.")

        info: YtDlpInfo = cast(Mapping[str, object], raw_info)
        entries: object = info.get("entries")
        if entries is not None:
            logger.debug(
                "yt-dlp extract_info returned entries operation=%s hostname=%r",
                operation,
                hostname,
            )
            if not isinstance(entries, Iterable):
                raise TrackSourceError("That link has no playable content.")

            first_entry: object = next(iter(entries), None)
            if not isinstance(first_entry, Mapping):
                raise TrackSourceError("That link has no playable content.")
            logger.debug(
                "yt-dlp extract_info call completed operation=%s hostname=%r result=first_entry",
                operation,
                hostname,
            )
            return cast(Mapping[str, object], first_entry)
        logger.debug(
            "yt-dlp extract_info call completed operation=%s hostname=%r result=single_entry",
            operation,
            hostname,
        )
        return info
