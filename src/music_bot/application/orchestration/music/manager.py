from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from music_bot.application.contracts.commands.music import PlaybackCommand
from music_bot.application.contracts.errors import PlaybackNotActiveError
from music_bot.application.contracts.results.music import PlaybackResult
from music_bot.application.orchestration.music.actor_registry import (
    GuildPlaybackActorRegistry,
)
from music_bot.application.orchestration.music.guild_playback_actor import (
    GuildPlaybackActor,
)


@dataclass(slots=True)
class _GuildLockEntry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    holders: int = 0


class GuildPlaybackActorManager:
    def __init__(self, *, actors: GuildPlaybackActorRegistry) -> None:
        self._actors: GuildPlaybackActorRegistry = actors
        self._guild_locks: dict[int, _GuildLockEntry] = {}

    async def execute[ResultT: PlaybackResult](self, command: PlaybackCommand[ResultT]) -> ResultT:
        async with self._guild_lock(guild_id=command.guild_id):
            actor: GuildPlaybackActor | None = self._actors.get(guild_id=command.guild_id)
            if actor is None:
                if not command.creates_actor:
                    raise PlaybackNotActiveError

                actor = await self._actors.create_or_restore(guild_id=command.guild_id)

            return await actor.execute(command)

    async def remove(self, *, guild_id: int) -> None:
        async with self._guild_lock(guild_id=guild_id):
            await self._actors.remove(guild_id=guild_id)

    async def shutdown(self) -> None:
        await self._actors.shutdown()

    @asynccontextmanager
    async def _guild_lock(self, *, guild_id: int) -> AsyncIterator[None]:
        entry: _GuildLockEntry | None = self._guild_locks.get(guild_id)
        if entry is None:
            entry = _GuildLockEntry()
            self._guild_locks[guild_id] = entry
        entry.holders += 1

        try:
            async with entry.lock:
                yield
        finally:
            entry.holders -= 1
            if entry.holders == 0 and self._guild_locks.get(guild_id) is entry:
                del self._guild_locks[guild_id]
