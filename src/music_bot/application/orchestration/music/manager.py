from __future__ import annotations

import asyncio
import logging
from asyncio import Future
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from time import perf_counter

from music_bot.application.contracts.commands.music import PlaybackCommand
from music_bot.application.contracts.errors import PlaybackNotActiveError
from music_bot.application.contracts.results.music import PlaybackResult
from music_bot.application.orchestration.music.actor_registry import (
    GuildPlaybackActorRegistry,
)
from music_bot.application.orchestration.music.guild_playback_actor import (
    GuildPlaybackActor,
)

logger: logging.Logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _GuildLockEntry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    holders: int = 0


class GuildPlaybackActorManager:
    def __init__(self, *, actors: GuildPlaybackActorRegistry) -> None:
        self._actors: GuildPlaybackActorRegistry = actors
        self._guild_locks: dict[int, _GuildLockEntry] = {}

    async def execute[ResultT: PlaybackResult](self, command: PlaybackCommand[ResultT]) -> ResultT:
        command_name: str = type(command).__name__
        started_at: float = perf_counter()
        logger.info(
            "Playback use case started command=%s guild_id=%s requested_by=%s creates_actor=%s",
            command_name,
            command.guild_id,
            command.requested_by,
            command.creates_actor,
        )
        try:
            async with self._guild_lock(guild_id=command.guild_id):
                actor: GuildPlaybackActor | None = self._actors.get(guild_id=command.guild_id)
                if actor is None:
                    if not command.creates_actor:
                        logger.info(
                            "Playback use case rejected without actor command=%s guild_id=%s",
                            command_name,
                            command.guild_id,
                        )
                        raise PlaybackNotActiveError

                    logger.debug(
                        "Creating playback actor for use case command=%s guild_id=%s",
                        command_name,
                        command.guild_id,
                    )
                    actor = await self._actors.create_or_restore(guild_id=command.guild_id)
                result_future: Future[ResultT] = actor.submit(command)

            result: ResultT = await result_future
        except Exception as exc:
            logger.warning(
                "Playback use case failed command=%s guild_id=%s error_type=%s elapsed_ms=%.2f",
                command_name,
                command.guild_id,
                type(exc).__name__,
                (perf_counter() - started_at) * 1000,
            )
            raise

        logger.info(
            "Playback use case completed command=%s guild_id=%s result=%s elapsed_ms=%.2f",
            command_name,
            command.guild_id,
            type(result).__name__,
            (perf_counter() - started_at) * 1000,
        )
        return result

    async def remove(self, *, guild_id: int) -> None:
        logger.info("Playback removal requested guild_id=%s", guild_id)
        async with self._guild_lock(guild_id=guild_id):
            await self._actors.remove(guild_id=guild_id)
        logger.info("Playback removed guild_id=%s", guild_id)

    async def shutdown(self) -> None:
        logger.info("Playback manager shutdown started")
        await self._actors.shutdown()
        logger.info("Playback manager shutdown completed")

    @asynccontextmanager
    async def _guild_lock(self, *, guild_id: int) -> AsyncIterator[None]:
        entry: _GuildLockEntry | None = self._guild_locks.get(guild_id)
        if entry is None:
            entry = _GuildLockEntry()
            self._guild_locks[guild_id] = entry
        entry.holders += 1
        logger.debug(
            "Playback guild lock requested guild_id=%s holders=%s locked=%s",
            guild_id,
            entry.holders,
            entry.lock.locked(),
        )

        try:
            async with entry.lock:
                logger.debug("Playback guild lock acquired guild_id=%s", guild_id)
                yield
        finally:
            entry.holders -= 1
            logger.debug(
                "Playback guild lock released guild_id=%s remaining_holders=%s",
                guild_id,
                entry.holders,
            )
            if entry.holders == 0 and self._guild_locks.get(guild_id) is entry:
                del self._guild_locks[guild_id]
