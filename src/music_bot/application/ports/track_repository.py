from __future__ import annotations

from typing import Protocol

from music_bot.application.ports.track import StoredTrack


class TrackRepository(Protocol):
    async def get_by_url(self, *, url: str) -> StoredTrack | None: ...

    async def save(
        self,
        *,
        url: str,
        title: str,
        duration_seconds: int,
    ) -> StoredTrack: ...
