from __future__ import annotations

import pytest

from music_bot.application.ports.track_source import TrackMetadata, TrackSource


class FakeTrackSource(TrackSource):
    def __init__(self, *, selected_source: TrackSource | None = None) -> None:
        self.calls: list[str] = []
        self._selected_source: TrackSource | None = selected_source

    async def validate_url(self, *, source_url: str) -> TrackSource:
        self.calls.append("validate")
        return self._selected_source or self

    async def _resolve_metadata(self, *, source_url: str) -> TrackMetadata:
        self.calls.append("metadata")
        return TrackMetadata(url=source_url, title="track", duration_seconds=1)

    async def _resolve_stream(self, *, source_url: str) -> str:
        self.calls.append("stream")
        return f"{source_url}#stream"


@pytest.mark.unit
async def test_validates_url_before_metadata_fetch() -> None:
    source = FakeTrackSource()

    await source.resolve_metadata(source_url="https://example.com/track")

    assert source.calls == ["validate", "metadata"]


@pytest.mark.unit
async def test_validates_url_before_stream_fetch() -> None:
    source = FakeTrackSource()

    await source.resolve_stream(source_url="https://example.com/track")

    assert source.calls == ["validate", "stream"]


@pytest.mark.unit
async def test_resolves_with_source_selected_by_validation() -> None:
    selected = FakeTrackSource()
    router = FakeTrackSource(selected_source=selected)

    metadata = await router.resolve_metadata(source_url="https://example.com/track")

    assert metadata.title == "track"
    assert router.calls == ["validate"]
    assert selected.calls == ["metadata"]
