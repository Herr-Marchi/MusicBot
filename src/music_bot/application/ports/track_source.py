from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import final


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackMetadata:
    url: str
    title: str
    duration_seconds: int


class TrackSourceError(Exception):
    pass


class TrackNotOwnedError(TrackSourceError):
    pass


class TrackMetadataResolver(ABC):
    @final
    async def resolve_metadata(self, *, source_url: str) -> TrackMetadata:
        source: TrackSource = await self.validate_url(source_url=source_url)
        return await source._resolve_metadata(source_url=source_url)

    @abstractmethod
    async def validate_url(self, *, source_url: str) -> TrackSource: ...

    @abstractmethod
    async def _resolve_metadata(self, *, source_url: str) -> TrackMetadata: ...


class TrackStreamResolver(ABC):
    @final
    async def resolve_stream(self, *, source_url: str) -> str:
        source: TrackSource = await self.validate_url(source_url=source_url)
        return await source._resolve_stream(source_url=source_url)

    @abstractmethod
    async def validate_url(self, *, source_url: str) -> TrackSource: ...

    @abstractmethod
    async def _resolve_stream(self, *, source_url: str) -> str: ...


class TrackSource(TrackMetadataResolver, TrackStreamResolver, ABC):
    pass
