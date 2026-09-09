from __future__ import annotations

from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock

import pytest
from yt_dlp.utils import DownloadError

from music_bot.adapters.outbound.url_safety import UnsafeUrlError
from music_bot.adapters.outbound.yt_dlp.base import YtDlpTrackSource
from music_bot.application.ports.track_source import TrackNotOwnedError, TrackSourceError


class _FakeTrackSource(YtDlpTrackSource):
    """Site-agnostic stand-in used to test the shared yt-dlp plumbing
    without depending on any real site's host names."""

    SOURCE_HOSTS: ClassVar[frozenset[str]] = frozenset({"example.com", "example.test"})
    STREAM_HOST_SUFFIXES: ClassVar[frozenset[str]] = frozenset({"cdn.example.com"})


@pytest.fixture
def allow_safe_url(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    check = AsyncMock()
    monkeypatch.setattr(
        "music_bot.adapters.outbound.yt_dlp.base.ensure_safe_url",
        check,
    )
    return check


@pytest.mark.unit
class TestYtDlpTrackSource:
    async def test_resolve_metadata_maps_yt_dlp_result(
        self,
        monkeypatch: pytest.MonkeyPatch,
        allow_safe_url: AsyncMock,
    ) -> None:
        youtube_dl = MagicMock()
        youtube_dl.__enter__.return_value.extract_info.return_value = {
            "webpage_url": "https://example.com/watch?v=id",
            "title": "Song",
            "duration": 123,
        }
        monkeypatch.setattr(
            "music_bot.adapters.outbound.yt_dlp.base.YoutubeDL",
            MagicMock(return_value=youtube_dl),
        )

        metadata = await _FakeTrackSource().resolve_metadata(source_url="https://example.test/id")

        assert metadata.url == "https://example.com/watch?v=id"
        assert metadata.title == "Song"
        assert metadata.duration_seconds == 123
        assert allow_safe_url.await_args_list == [
            (("https://example.test/id",), {}),
            (("https://example.com/watch?v=id",), {}),
        ]

    async def test_resolve_stream_returns_direct_url(
        self,
        monkeypatch: pytest.MonkeyPatch,
        allow_safe_url: AsyncMock,
    ) -> None:
        youtube_dl = MagicMock()
        youtube_dl.__enter__.return_value.extract_info.return_value = {
            "url": "https://cdn.example.com/audio"
        }
        monkeypatch.setattr(
            "music_bot.adapters.outbound.yt_dlp.base.YoutubeDL",
            MagicMock(return_value=youtube_dl),
        )

        stream_url = await _FakeTrackSource().resolve_stream(source_url="https://example.test/id")

        assert stream_url == "https://cdn.example.com/audio"
        assert allow_safe_url.await_args_list == [
            (("https://example.test/id",), {}),
            (("https://cdn.example.com/audio",), {}),
        ]

    async def test_rejects_unowned_url_before_safety_check(self, allow_safe_url: AsyncMock) -> None:
        with pytest.raises(TrackSourceError):
            await _FakeTrackSource().resolve_metadata(source_url="https://attacker.test/track")

        allow_safe_url.assert_not_awaited()

    async def test_rejects_host_allowlist_bypass_before_safety_check(
        self, allow_safe_url: AsyncMock
    ) -> None:
        with pytest.raises(TrackNotOwnedError):
            await _FakeTrackSource().resolve_metadata(
                source_url="https://example.com.attacker.test/watch?v=id"
            )

        allow_safe_url.assert_not_awaited()

    async def test_unsafe_input_never_reaches_ytdlp(
        self,
        monkeypatch: pytest.MonkeyPatch,
        allow_safe_url: AsyncMock,
    ) -> None:
        allow_safe_url.side_effect = UnsafeUrlError("unsafe")
        youtube_dl_factory = MagicMock()
        monkeypatch.setattr(
            "music_bot.adapters.outbound.yt_dlp.base.YoutubeDL",
            youtube_dl_factory,
        )

        with pytest.raises(TrackSourceError, match="unsafe"):
            await _FakeTrackSource().resolve_metadata(source_url="https://example.test/id")

        youtube_dl_factory.assert_not_called()

    async def test_rejects_unsupported_canonical_metadata_url(
        self,
        monkeypatch: pytest.MonkeyPatch,
        allow_safe_url: AsyncMock,
    ) -> None:
        youtube_dl = MagicMock()
        youtube_dl.__enter__.return_value.extract_info.return_value = {
            "webpage_url": "https://attacker.test/track",
            "title": "Song",
            "duration": 1,
        }
        monkeypatch.setattr(
            "music_bot.adapters.outbound.yt_dlp.base.YoutubeDL",
            MagicMock(return_value=youtube_dl),
        )

        with pytest.raises(TrackNotOwnedError):
            await _FakeTrackSource().resolve_metadata(source_url="https://example.test/id")

        allow_safe_url.assert_awaited_once_with("https://example.test/id")

    @pytest.mark.parametrize(
        "stream_url",
        [
            "https://cdn.example.com.attacker.test/audio",
            "https://evilcdn.example.com/audio",
            "https://attacker.test/cdn.example.com/audio",
        ],
    )
    async def test_rejects_stream_host_allowlist_bypass(
        self,
        stream_url: str,
        monkeypatch: pytest.MonkeyPatch,
        allow_safe_url: AsyncMock,
    ) -> None:
        youtube_dl = MagicMock()
        youtube_dl.__enter__.return_value.extract_info.return_value = {"url": stream_url}
        monkeypatch.setattr(
            "music_bot.adapters.outbound.yt_dlp.base.YoutubeDL",
            MagicMock(return_value=youtube_dl),
        )

        with pytest.raises(TrackSourceError, match="stream URL is not supported"):
            await _FakeTrackSource().resolve_stream(source_url="https://example.test/id")

        allow_safe_url.assert_awaited_once_with("https://example.test/id")

    async def test_rejects_unsafe_allowed_stream_before_returning_it(
        self,
        monkeypatch: pytest.MonkeyPatch,
        allow_safe_url: AsyncMock,
    ) -> None:
        stream_url = "https://cdn.example.com/audio"
        allow_safe_url.side_effect = [None, UnsafeUrlError("private address")]
        youtube_dl = MagicMock()
        youtube_dl.__enter__.return_value.extract_info.return_value = {"url": stream_url}
        monkeypatch.setattr(
            "music_bot.adapters.outbound.yt_dlp.base.YoutubeDL",
            MagicMock(return_value=youtube_dl),
        )

        with pytest.raises(TrackSourceError, match="private address"):
            await _FakeTrackSource().resolve_stream(source_url="https://example.test/id")

        assert allow_safe_url.await_count == 2

    async def test_download_error_does_not_leak_internal_detail(
        self,
        monkeypatch: pytest.MonkeyPatch,
        allow_safe_url: AsyncMock,
    ) -> None:
        sensitive_detail = "Connection refused to 10.0.0.5:8080"
        youtube_dl = MagicMock()
        youtube_dl.__enter__.return_value.extract_info.side_effect = DownloadError(sensitive_detail)
        monkeypatch.setattr(
            "music_bot.adapters.outbound.yt_dlp.base.YoutubeDL",
            MagicMock(return_value=youtube_dl),
        )

        with pytest.raises(TrackSourceError) as exc_info:
            await _FakeTrackSource().resolve_metadata(source_url="https://example.test/id")

        assert sensitive_detail not in str(exc_info.value)
