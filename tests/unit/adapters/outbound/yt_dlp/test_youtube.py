from __future__ import annotations

import socket
from typing import Any
from unittest.mock import MagicMock

import pytest
from yt_dlp.utils import DownloadError

from music_bot.adapters.outbound.yt_dlp.youtube import YtDlpTrackSource, ensure_safe_track_url
from music_bot.application.contracts.errors import TrackMetadataResolutionError


@pytest.mark.unit
class TestEnsureSafeTrackUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "ftp://example.com/file",
            "javascript:alert(1)",
            "",
        ],
    )
    def test_rejects_disallowed_scheme(self, url: str) -> None:
        with pytest.raises(TrackMetadataResolutionError):
            ensure_safe_track_url(url)

    def test_rejects_url_with_no_host(self) -> None:
        with pytest.raises(TrackMetadataResolutionError):
            ensure_safe_track_url("https:///no-host-here")

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/",
            "http://127.0.0.1:8080/admin",
            "http://[::1]/",
            "http://169.254.169.254/latest/meta-data/",  # cloud metadata service
            "http://10.0.0.5/",
            "http://172.16.0.1/",
            "http://192.168.1.1/",
            "http://0.0.0.0/",
        ],
    )
    def test_rejects_literal_unsafe_addresses(self, url: str) -> None:
        with pytest.raises(TrackMetadataResolutionError):
            ensure_safe_track_url(url)

    def test_allows_literal_public_address(self) -> None:
        ensure_safe_track_url("http://93.184.216.34/")

    def test_rejects_hostname_resolving_to_private_address(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_getaddrinfo(host: str, port: object, *args: object, **kwargs: object) -> Any:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

        with pytest.raises(TrackMetadataResolutionError):
            ensure_safe_track_url("http://internal.example.test/")

    def test_allows_hostname_resolving_to_public_address(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_getaddrinfo(host: str, port: object, *args: object, **kwargs: object) -> Any:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

        ensure_safe_track_url("http://public.example.test/")

    def test_rejects_hostname_that_does_not_resolve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_getaddrinfo(host: str, port: object, *args: object, **kwargs: object) -> Any:
            raise socket.gaierror("Name or service not known")

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

        with pytest.raises(TrackMetadataResolutionError):
            ensure_safe_track_url("http://does-not-resolve.example.test/")


@pytest.mark.unit
class TestYtDlpTrackSourceErrorMessages:
    async def test_download_error_does_not_leak_internal_detail_to_caller(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sensitive_detail: str = "Connection refused to 10.0.0.5:8080 - internal-admin-panel"

        fake_ydl = MagicMock()
        fake_ydl.__enter__.return_value.extract_info.side_effect = DownloadError(sensitive_detail)
        monkeypatch.setattr(
            "music_bot.adapters.outbound.yt_dlp.youtube.YoutubeDL",
            MagicMock(return_value=fake_ydl),
        )

        source = YtDlpTrackSource()
        with pytest.raises(TrackMetadataResolutionError) as exc_info:
            await source.resolve(source_url="http://example.com/track")

        assert sensitive_detail not in str(exc_info.value)
        assert "10.0.0.5" not in str(exc_info.value)


def _mock_youtube_dl(monkeypatch: pytest.MonkeyPatch, extract_info: Any) -> list[str]:
    """Patches YoutubeDL so extract_info() is replaced by `extract_info`,
    and returns the list its calls will be recorded into."""
    captured_urls: list[str] = []

    def recording_extract_info(url: str, download: bool) -> Any:
        captured_urls.append(url)
        return extract_info(url)

    fake_ydl = MagicMock()
    fake_ydl.__enter__.return_value.extract_info.side_effect = recording_extract_info
    monkeypatch.setattr(
        "music_bot.adapters.outbound.yt_dlp.youtube.YoutubeDL",
        MagicMock(return_value=fake_ydl),
    )
    return captured_urls


@pytest.mark.unit
class TestResolveSearchesInsteadOfFetchingDirectly:
    async def test_resolve_wraps_input_as_a_youtube_search_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured_urls = _mock_youtube_dl(
            monkeypatch,
            lambda _url: {
                "entries": [
                    {
                        "webpage_url": "https://www.youtube.com/watch?v=abc123",
                        "title": "Never Gonna Give You Up",
                        "duration": 213,
                    }
                ]
            },
        )

        source = YtDlpTrackSource()
        metadata = await source.resolve(source_url="never gonna give you up")

        assert captured_urls == ["ytsearch1:never gonna give you up"]
        assert metadata.source_url == "https://www.youtube.com/watch?v=abc123"
        assert metadata.title == "Never Gonna Give You Up"

    async def test_ssrf_shaped_input_is_treated_as_search_text_not_a_fetch_target(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A string that would be rejected outright by ensure_safe_track_url()
        # if it were fetched as a URL must not be rejected here — resolve()
        # never treats it as a URL at all, it's just the search query.
        captured_urls = _mock_youtube_dl(monkeypatch, lambda _url: {"entries": []})

        source = YtDlpTrackSource()
        with pytest.raises(TrackMetadataResolutionError) as exc_info:
            await source.resolve(source_url="http://169.254.169.254/latest/meta-data/")

        assert captured_urls == ["ytsearch1:http://169.254.169.254/latest/meta-data/"]
        assert "cannot be used" not in str(exc_info.value)  # not the URL-safety rejection
        assert str(exc_info.value) == "No results found for that search."

    async def test_no_search_results_raises_a_clear_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_youtube_dl(monkeypatch, lambda _url: {"entries": []})

        source = YtDlpTrackSource()
        with pytest.raises(TrackMetadataResolutionError, match="No results found"):
            await source.resolve(source_url="asdkjqwhekjqwhekjqhwekjqhwe")


@pytest.mark.unit
class TestResolveStreamStillValidatesTheUrl:
    async def test_rejects_unsafe_resolved_url_before_fetching(self) -> None:
        # resolve_stream() receives an already-resolved URL (from a prior
        # resolve() call's canonical webpage_url) — it's the one path that
        # still hands yt-dlp a real destination, so the host check applies.
        source = YtDlpTrackSource()

        with pytest.raises(TrackMetadataResolutionError):
            await source.resolve_stream(source_url="http://169.254.169.254/latest/meta-data/")
