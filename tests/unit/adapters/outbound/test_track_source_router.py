from __future__ import annotations

from urllib.parse import urlsplit

import pytest

from music_bot.adapters.outbound.track_source_router import TrackSourceRouter
from music_bot.application.ports.track_source import (
    TrackMetadata,
    TrackNotOwnedError,
    TrackSource,
    TrackSourceError,
)


class FakeSource(TrackSource):
    def __init__(self, *, name: str, host: str) -> None:
        self._name: str = name
        self._host: str = host
        self.validate_calls: list[str] = []
        self.metadata_calls: list[str] = []
        self.stream_calls: list[str] = []

    async def validate_url(self, *, source_url: str) -> TrackSource:
        self.validate_calls.append(source_url)
        if urlsplit(source_url).hostname != self._host:
            raise TrackNotOwnedError("not owned")
        return self

    async def _resolve_metadata(self, *, source_url: str) -> TrackMetadata:
        self.metadata_calls.append(source_url)
        return TrackMetadata(url=source_url, title=self._name, duration_seconds=1)

    async def _resolve_stream(self, *, source_url: str) -> str:
        self.stream_calls.append(source_url)
        return f"{source_url}#{self._name}"


class FailingValidationSource(FakeSource):
    async def validate_url(self, *, source_url: str) -> TrackSource:
        self.validate_calls.append(source_url)
        raise TrackSourceError("unsafe URL")


@pytest.mark.unit
class TestTrackSourceRouter:
    async def test_routes_metadata_to_matching_source(self) -> None:
        youtube = FakeSource(name="youtube", host="youtube.com")
        soundcloud = FakeSource(name="soundcloud", host="soundcloud.com")
        router = TrackSourceRouter(sources=(youtube, soundcloud))

        metadata: TrackMetadata = await router.resolve_metadata(
            source_url="https://soundcloud.com/a/b"
        )

        assert metadata.title == "soundcloud"
        assert youtube.validate_calls == ["https://soundcloud.com/a/b"]
        assert soundcloud.validate_calls == ["https://soundcloud.com/a/b"]
        assert youtube.metadata_calls == []
        assert soundcloud.metadata_calls == ["https://soundcloud.com/a/b"]

    async def test_routes_stream_to_matching_source(self) -> None:
        youtube = FakeSource(name="youtube", host="youtube.com")
        router = TrackSourceRouter(sources=(youtube,))

        stream_url: str = await router.resolve_stream(source_url="https://youtube.com/watch?v=id")

        assert stream_url == "https://youtube.com/watch?v=id#youtube"
        assert youtube.validate_calls == ["https://youtube.com/watch?v=id"]
        assert youtube.stream_calls == ["https://youtube.com/watch?v=id"]

    async def test_raises_public_error_when_no_source_matches(self) -> None:
        router = TrackSourceRouter(sources=(FakeSource(name="youtube", host="youtube.com"),))

        with pytest.raises(TrackSourceError) as exc_info:
            await router.resolve_metadata(source_url="https://example.com/track")

        assert isinstance(exc_info.value, TrackNotOwnedError)

    async def test_empty_router_rejects_both_resolution_paths(self) -> None:
        router = TrackSourceRouter(sources=())

        with pytest.raises(TrackNotOwnedError):
            await router.resolve_metadata(source_url="https://example.com/track")
        with pytest.raises(TrackNotOwnedError):
            await router.resolve_stream(source_url="https://example.com/track")

    async def test_does_not_treat_safety_failure_as_routing_miss(self) -> None:
        unsafe = FailingValidationSource(name="unsafe", host="example.com")
        fallback = FakeSource(name="fallback", host="example.com")
        router = TrackSourceRouter(sources=(unsafe, fallback))

        with pytest.raises(TrackSourceError, match="unsafe URL"):
            await router.resolve_metadata(source_url="https://example.com/track")

        assert fallback.validate_calls == []
        assert fallback.metadata_calls == []

    async def test_nested_router_returns_leaf_without_revalidating_it(self) -> None:
        leaf = FakeSource(name="leaf", host="example.com")
        router = TrackSourceRouter(sources=(TrackSourceRouter(sources=(leaf,)),))

        metadata = await router.resolve_metadata(source_url="https://example.com/track")

        assert metadata.title == "leaf"
        assert leaf.validate_calls == ["https://example.com/track"]
        assert leaf.metadata_calls == ["https://example.com/track"]

    async def test_first_matching_source_wins(self) -> None:
        first = FakeSource(name="first", host="example.com")
        second = FakeSource(name="second", host="example.com")
        router = TrackSourceRouter(sources=(first, second))

        metadata: TrackMetadata = await router.resolve_metadata(
            source_url="https://example.com/track"
        )

        assert metadata.title == "first"
        assert first.validate_calls == ["https://example.com/track"]
        assert second.validate_calls == []
        assert first.metadata_calls == ["https://example.com/track"]
        assert second.metadata_calls == []
