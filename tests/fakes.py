from __future__ import annotations

from music_bot.application.ports.track_catalog import CatalogedTrack
from music_bot.application.ports.track_source import TrackMetadata


class FakeTrackSource:
    def __init__(self) -> None:
        self.resolve_calls: list[str] = []
        self.resolve_stream_calls: list[str] = []
        self._metadata_by_url: dict[str, TrackMetadata] = {}
        self._resolve_error: Exception | None = None

    def set_metadata(
        self,
        source_url: str,
        *,
        title: str,
        duration_seconds: int = 100,
        canonical_url: str | None = None,
    ) -> None:
        self._metadata_by_url[source_url] = TrackMetadata(
            source_url=canonical_url or source_url,
            title=title,
            duration_seconds=duration_seconds,
        )

    def fail_resolve_with(self, error: Exception) -> None:
        self._resolve_error = error

    async def resolve(self, *, source_url: str) -> TrackMetadata:
        self.resolve_calls.append(source_url)

        if self._resolve_error is not None:
            raise self._resolve_error

        return self._metadata_by_url.get(source_url) or TrackMetadata(
            source_url=source_url,
            title=source_url,
            duration_seconds=100,
        )

    async def resolve_stream(self, *, source_url: str) -> str:
        self.resolve_stream_calls.append(source_url)
        return f"{source_url}#stream"


class FakeTrackCatalog:
    def __init__(self) -> None:
        self.get_calls: list[str] = []
        self.upsert_calls: list[tuple[str, str, int]] = []
        self._by_url: dict[str, CatalogedTrack] = {}

    def seed(self, url: str, *, title: str, duration_seconds: int) -> None:
        self._by_url[url] = CatalogedTrack(
            url=url,
            title=title,
            duration_seconds=duration_seconds,
        )

    async def get(self, *, url: str) -> CatalogedTrack | None:
        self.get_calls.append(url)
        return self._by_url.get(url)

    async def upsert(
        self,
        *,
        url: str,
        title: str,
        duration_seconds: int,
    ) -> CatalogedTrack:
        self.upsert_calls.append((url, title, duration_seconds))
        cataloged = CatalogedTrack(
            url=url,
            title=title,
            duration_seconds=duration_seconds,
        )
        self._by_url[url] = cataloged
        return cataloged
