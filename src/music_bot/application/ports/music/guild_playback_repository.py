from __future__ import annotations

from typing import Protocol

from music_bot.domain.music.models import GuildPlayback


class GuildPlaybackRepository(Protocol):
    async def get(self, *, guild_id: int) -> GuildPlayback | None: ...

    async def save(self, *, playback: GuildPlayback) -> None: ...

    async def delete(self, *, guild_id: int) -> None: ...
