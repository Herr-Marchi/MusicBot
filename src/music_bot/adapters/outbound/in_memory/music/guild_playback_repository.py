from __future__ import annotations

from copy import deepcopy

from music_bot.domain.music.models import GuildPlayback


class InMemoryGuildPlaybackRepository:
    def __init__(self) -> None:
        self._playbacks: dict[int, GuildPlayback] = {}

    async def get(self, *, guild_id: int) -> GuildPlayback | None:
        playback: GuildPlayback | None = self._playbacks.get(guild_id)
        return deepcopy(playback) if playback is not None else None

    async def save(self, *, playback: GuildPlayback) -> None:
        self._playbacks[playback.guild_id] = deepcopy(playback)

    async def delete(self, *, guild_id: int) -> None:
        self._playbacks.pop(guild_id, None)
