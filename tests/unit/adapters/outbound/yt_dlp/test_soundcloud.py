from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from yt_dlp.utils import DownloadError

from music_bot.adapters.outbound.url_safety import UnsafeUrlError
from music_bot.adapters.outbound.yt_dlp.soundcloud import SoundCloudTrackSource
from music_bot.application.ports.track_source import TrackNotOwnedError, TrackSourceError


@pytest.fixture
def allow_safe_url(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    check = AsyncMock()
    monkeypatch.setattr(
        "music_bot.adapters.outbound.yt_dlp.base.ensure_safe_url",
        check,
    )
    return check


@pytest.mark.unit
class TestSoundCloudTrackSource:
    async def test_resolve_metadata_maps_yt_dlp_result(
        self,
        monkeypatch: pytest.MonkeyPatch,
        allow_safe_url: AsyncMock,
    ) -> None:
        ytdlp = MagicMock()
        ytdlp.__enter__.return_value.extract_info.return_value = {
            "webpage_url": "https://soundcloud.com/artist/track",
            "title": "Song",
            "duration": 123,
        }
        monkeypatch.setattr(
            "music_bot.adapters.outbound.yt_dlp.base.YoutubeDL",
            MagicMock(return_value=ytdlp),
        )

        metadata = await SoundCloudTrackSource().resolve_metadata(
            source_url="https://soundcloud.com/artist/track"
        )

        assert metadata.url == "https://soundcloud.com/artist/track"
        assert metadata.title == "Song"
        assert metadata.duration_seconds == 123
        assert allow_safe_url.await_args_list == [
            (("https://soundcloud.com/artist/track",), {}),
            (("https://soundcloud.com/artist/track",), {}),
        ]

    async def test_resolve_stream_returns_direct_url(
        self,
        monkeypatch: pytest.MonkeyPatch,
        allow_safe_url: AsyncMock,
    ) -> None:
        ytdlp = MagicMock()
        ytdlp.__enter__.return_value.extract_info.return_value = {
            "url": "https://cf-media.sndcdn.com/stream.mp3"
        }
        monkeypatch.setattr(
            "music_bot.adapters.outbound.yt_dlp.base.YoutubeDL",
            MagicMock(return_value=ytdlp),
        )

        stream_url = await SoundCloudTrackSource().resolve_stream(
            source_url="https://soundcloud.com/artist/track"
        )

        assert stream_url == "https://cf-media.sndcdn.com/stream.mp3"
        assert allow_safe_url.await_args_list == [
            (("https://soundcloud.com/artist/track",), {}),
            (("https://cf-media.sndcdn.com/stream.mp3",), {}),
        ]

    async def test_rejects_non_soundcloud_url_before_safety_check(
        self, allow_safe_url: AsyncMock
    ) -> None:
        with pytest.raises(TrackSourceError):
            await SoundCloudTrackSource().resolve_metadata(source_url="https://example.com/track")

        allow_safe_url.assert_not_awaited()

    async def test_rejects_host_allowlist_bypass_before_safety_check(
        self, allow_safe_url: AsyncMock
    ) -> None:
        with pytest.raises(TrackNotOwnedError):
            await SoundCloudTrackSource().resolve_metadata(
                source_url="https://soundcloud.com.attacker.test/artist/track"
            )

        allow_safe_url.assert_not_awaited()

    async def test_unsafe_input_never_reaches_ytdlp(
        self,
        monkeypatch: pytest.MonkeyPatch,
        allow_safe_url: AsyncMock,
    ) -> None:
        allow_safe_url.side_effect = UnsafeUrlError("unsafe")
        ytdlp_factory = MagicMock()
        monkeypatch.setattr(
            "music_bot.adapters.outbound.yt_dlp.base.YoutubeDL",
            ytdlp_factory,
        )

        with pytest.raises(TrackSourceError, match="unsafe"):
            await SoundCloudTrackSource().resolve_metadata(
                source_url="https://soundcloud.com/artist/track"
            )

        ytdlp_factory.assert_not_called()

    async def test_rejects_unsupported_canonical_metadata_url(
        self,
        monkeypatch: pytest.MonkeyPatch,
        allow_safe_url: AsyncMock,
    ) -> None:
        ytdlp = MagicMock()
        ytdlp.__enter__.return_value.extract_info.return_value = {
            "webpage_url": "https://attacker.test/track",
            "title": "Song",
            "duration": 1,
        }
        monkeypatch.setattr(
            "music_bot.adapters.outbound.yt_dlp.base.YoutubeDL",
            MagicMock(return_value=ytdlp),
        )

        with pytest.raises(TrackNotOwnedError):
            await SoundCloudTrackSource().resolve_metadata(
                source_url="https://soundcloud.com/artist/track"
            )

        allow_safe_url.assert_awaited_once_with("https://soundcloud.com/artist/track")

    @pytest.mark.parametrize(
        "stream_url",
        [
            "https://sndcdn.com.attacker.test/audio",
            "https://evilsndcdn.com/audio",
            "https://attacker.test/sndcdn.com/audio",
        ],
    )
    async def test_rejects_stream_host_allowlist_bypass(
        self,
        stream_url: str,
        monkeypatch: pytest.MonkeyPatch,
        allow_safe_url: AsyncMock,
    ) -> None:
        ytdlp = MagicMock()
        ytdlp.__enter__.return_value.extract_info.return_value = {"url": stream_url}
        monkeypatch.setattr(
            "music_bot.adapters.outbound.yt_dlp.base.YoutubeDL",
            MagicMock(return_value=ytdlp),
        )

        with pytest.raises(TrackSourceError, match="stream URL is not supported"):
            await SoundCloudTrackSource().resolve_stream(
                source_url="https://soundcloud.com/artist/track"
            )

        allow_safe_url.assert_awaited_once_with("https://soundcloud.com/artist/track")

    async def test_rejects_unsafe_allowed_stream_before_returning_it(
        self,
        monkeypatch: pytest.MonkeyPatch,
        allow_safe_url: AsyncMock,
    ) -> None:
        stream_url = "https://cf-media.sndcdn.com/stream.mp3"
        allow_safe_url.side_effect = [None, UnsafeUrlError("private address")]
        ytdlp = MagicMock()
        ytdlp.__enter__.return_value.extract_info.return_value = {"url": stream_url}
        monkeypatch.setattr(
            "music_bot.adapters.outbound.yt_dlp.base.YoutubeDL",
            MagicMock(return_value=ytdlp),
        )

        with pytest.raises(TrackSourceError, match="private address"):
            await SoundCloudTrackSource().resolve_stream(
                source_url="https://soundcloud.com/artist/track"
            )

        assert allow_safe_url.await_count == 2

    async def test_download_error_does_not_leak_internal_detail(
        self,
        monkeypatch: pytest.MonkeyPatch,
        allow_safe_url: AsyncMock,
    ) -> None:
        sensitive_detail = "Connection refused to 10.0.0.5:8080"
        ytdlp = MagicMock()
        ytdlp.__enter__.return_value.extract_info.side_effect = DownloadError(sensitive_detail)
        monkeypatch.setattr(
            "music_bot.adapters.outbound.yt_dlp.base.YoutubeDL",
            MagicMock(return_value=ytdlp),
        )

        with pytest.raises(TrackSourceError) as exc_info:
            await SoundCloudTrackSource().resolve_metadata(
                source_url="https://soundcloud.com/artist/track"
            )

        assert sensitive_detail not in str(exc_info.value)
