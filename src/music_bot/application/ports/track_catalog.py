from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogedTrack:
    url: str
    title: str
    duration_seconds: int


class TrackCatalog(Protocol):
    async def get(self, *, url: str) -> CatalogedTrack | None: ...

    async def upsert(
        self,
        *,
        url: str,
        title: str,
        duration_seconds: int,
    ) -> CatalogedTrack: ...
