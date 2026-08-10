from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackMetadata:
    source_url: str
    title: str
    duration_seconds: int


class TrackMetadataResolver(Protocol):
    async def resolve(self, *, source_url: str) -> TrackMetadata: ...


class TrackStreamResolver(Protocol):
    async def resolve_stream(self, *, source_url: str) -> str: ...


class TrackSource(TrackMetadataResolver, TrackStreamResolver, Protocol):
    pass
