from __future__ import annotations

import asyncio

import pytest
from tests.fakes import FakeGuildPlayer, FakeTrackSource

from music_bot.adapters.outbound.in_memory.music import InMemoryGuildPlaybackRepository
from music_bot.application.contracts.commands.music import GetQueueCommand
from music_bot.application.contracts.errors import PlaybackNotActiveError
from music_bot.application.orchestration.music.actor_registry import (
    GuildPlaybackActorRegistry,
)
from music_bot.application.orchestration.music.manager import GuildPlaybackActorManager


def _make_manager() -> GuildPlaybackActorManager:
    registry = GuildPlaybackActorRegistry(
        playback_repository=InMemoryGuildPlaybackRepository(),
        player_factory=lambda _guild_id: FakeGuildPlayer(),
        metadata_resolver=FakeTrackSource(),
    )
    return GuildPlaybackActorManager(actors=registry)


@pytest.mark.unit
class TestGuildLockCleanup:
    async def test_lock_entry_is_removed_after_execute_completes(self) -> None:
        manager: GuildPlaybackActorManager = _make_manager()

        with pytest.raises(PlaybackNotActiveError):
            await manager.execute(GetQueueCommand(guild_id=1, requested_by=1))

        assert manager._guild_locks == {}

    async def test_lock_entry_is_removed_after_remove_completes(self) -> None:
        manager: GuildPlaybackActorManager = _make_manager()

        await manager.remove(guild_id=1)

        assert manager._guild_locks == {}

    async def test_concurrent_holders_share_one_entry_until_the_last_releases(self) -> None:
        manager: GuildPlaybackActorManager = _make_manager()

        first_holding: asyncio.Event = asyncio.Event()
        release_first: asyncio.Event = asyncio.Event()

        async def hold_first() -> None:
            async with manager._guild_lock(guild_id=1):
                first_holding.set()
                await release_first.wait()

        first_task: asyncio.Task[None] = asyncio.create_task(hold_first())
        await asyncio.wait_for(first_holding.wait(), timeout=1)

        entry = manager._guild_locks[1]
        assert entry.holders == 1

        second_registered: asyncio.Event = asyncio.Event()

        async def hold_second() -> None:
            async with manager._guild_lock(guild_id=1):
                second_registered.set()

        second_task: asyncio.Task[None] = asyncio.create_task(hold_second())
        # second_task blocks acquiring entry.lock (first_task holds it), but
        # registering as a holder happens before that block — give it a turn.
        await asyncio.sleep(0)

        # Still the *same* entry — not removed-and-replaced by the second
        # caller arriving while the first is still active.
        assert manager._guild_locks[1] is entry
        assert entry.holders == 2

        release_first.set()
        await asyncio.wait_for(first_task, timeout=1)
        await asyncio.wait_for(second_task, timeout=1)

        assert manager._guild_locks == {}
