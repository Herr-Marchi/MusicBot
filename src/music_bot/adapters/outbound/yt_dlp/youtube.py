from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from music_bot.application.contracts.errors import TrackMetadataResolutionError
from music_bot.application.ports.track_source import TrackMetadata

logger: logging.Logger = logging.getLogger(__name__)

# Bounds each individual socket operation yt-dlp performs. asyncio.wait_for
# around the asyncio.to_thread() call below only makes the *caller* give up —
# the worker thread itself keeps running a hung socket read forever, since
# Python threads can't be cancelled from outside. This is what actually
# bounds it. Kept below the caller's own timeout so a slow-but-alive request
# has room to fail on its own first.
_SOCKET_TIMEOUT_SECONDS: float = 15.0

_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})


def _is_unsafe_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local  # includes 169.254.169.254 — cloud metadata services
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def ensure_safe_track_url(source_url: str) -> None:
    """Reject URLs yt-dlp shouldn't be let anywhere near.

    yt-dlp's generic extractor will happily fetch *any* http(s) URL a user
    supplies, from inside this container, with whatever network access this
    container has — Docker-internal services, cloud metadata endpoints,
    localhost. This blocks the obvious cases: disallowed schemes, and hosts
    that are literally or resolve to a private/loopback/link-local/reserved
    address. It does NOT protect against a same-scheme redirect to such an
    address, or DNS rebinding between this check and yt-dlp's own connection
    a moment later — closing those needs hooking yt-dlp's own request/redirect
    handling, which this does not do.
    """
    parsed = urlparse(source_url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise TrackMetadataResolutionError("Only http/https links are supported.")

    hostname: str | None = parsed.hostname
    if not hostname:
        raise TrackMetadataResolutionError("That URL has no host.")

    try:
        literal_address = ipaddress.ip_address(hostname)
    except ValueError:
        literal_address = None

    if literal_address is not None:
        if _is_unsafe_address(literal_address):
            raise TrackMetadataResolutionError("That URL cannot be used.")
        return

    try:
        resolved: list[tuple[Any, ...]] = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise TrackMetadataResolutionError("That URL's host could not be resolved.") from exc

    for _family, _type, _proto, _canonname, sockaddr in resolved:
        resolved_address = ipaddress.ip_address(sockaddr[0])
        if _is_unsafe_address(resolved_address):
            raise TrackMetadataResolutionError("That URL cannot be used.")


class YtDlpTrackSource:
    async def resolve(self, *, source_url: str) -> TrackMetadata:
        # source_url here is untrusted free text, not a link to fetch — it's
        # always routed through YouTube's own search rather than parsed and
        # connected to directly. That's what actually closes SSRF for this
        # path: the user's text never becomes a connection target, so there's
        # nothing for ensure_safe_track_url() to check. A "paste an exact
        # link" mode is a deliberately separate, not-yet-built path — that
        # one *would* hand a real destination to yt-dlp and needs the host
        # validation this one has no use for.
        search_query: str = f"ytsearch1:{source_url}"
        info = await asyncio.to_thread(
            self._extract_info,
            search_query,
            {
                "noplaylist": True,
                "quiet": True,
                "socket_timeout": _SOCKET_TIMEOUT_SECONDS,
            },
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

        return TrackMetadata(
            source_url=canonical_url,
            title=title,
            duration_seconds=duration_seconds,
        )

    async def resolve_stream(self, *, source_url: str) -> str:
        # Unlike resolve(), this always receives a real URL — the canonical
        # webpage_url a prior resolve() call already got back from YouTube's
        # own search — and that URL is what actually gets fetched. Kept
        # behind the same host check as defense in depth, even though under
        # the current call graph it's never directly user-supplied.
        # ensure_safe_track_url() does blocking DNS resolution, so it runs
        # inside the same to_thread() offload as the extraction itself,
        # not out here on the event loop.
        info = await asyncio.to_thread(
            self._extract_stream_info,
            source_url,
            {
                "format": "bestaudio/best",
                "noplaylist": True,
                "quiet": True,
                "socket_timeout": _SOCKET_TIMEOUT_SECONDS,
            },
        )

        raw_stream_url: object = info.get("url")
        if not isinstance(raw_stream_url, str) or not raw_stream_url:
            raise TrackMetadataResolutionError("yt-dlp could not resolve a playable audio URL")

        return raw_stream_url

    @staticmethod
    def _extract_stream_info(source_url: str, options: Any) -> Any:
        ensure_safe_track_url(source_url)
        return YtDlpTrackSource._extract_info(source_url, options)

    @staticmethod
    def _extract_info(source_url: str, options: Any) -> Any:
        try:
            with YoutubeDL(options) as youtube_dl:
                info = youtube_dl.extract_info(source_url, download=False)
        except DownloadError as exc:
            # yt-dlp's own message can echo back connection-level detail
            # about whatever it just tried to reach (timed out vs refused
            # vs a specific HTTP status) — exactly what an SSRF probe reads
            # to tell targets apart. Log it, never hand it to the user.
            logger.warning("yt-dlp failed to resolve %s: %s", source_url, exc)
            raise TrackMetadataResolutionError("Could not resolve that track.") from exc

        if info is None:
            raise TrackMetadataResolutionError("The track source returned no metadata")

        entries = info.get("entries")
        if entries is not None:
            first_entry = next(iter(entries), None)
            if first_entry is None:
                raise TrackMetadataResolutionError("No results found for that search.")
            info = first_entry

        return info
