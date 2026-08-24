from __future__ import annotations

import asyncio
import logging
from typing import cast

import pytest
from tests.fakes import FakeGuildPlayer, FakeTrackSource, FakeUoWFactory

from music_bot.adapters.outbound.in_memory.music import InMemoryGuildPlaybackRepository
from music_bot.application.contracts.commands.music import (
    GetQueueCommand,
    PlayPlaylistCommand,
)
from music_bot.application.contracts.errors import PlaybackNotActiveError
from music_bot.application.contracts.results.music import GetQueueResult, PlayPlaylistResult
from music_bot.application.orchestration.music.actor_registry import (
    GuildPlaybackActorRegistry,
)
from music_bot.application.orchestration.music.manager import GuildPlaybackActorManager
from music_bot.application.orchestration.playlists import PlaylistService
from music_bot.application.orchestration.track_service import TrackService


def _make_manager() -> GuildPlaybackActorManager:
    uow_factory: FakeUoWFactory = FakeUoWFactory()
    track_service: TrackService = TrackService(source=FakeTrackSource())
    registry: GuildPlaybackActorRegistry = GuildPlaybackActorRegistry(
        playback_repository=InMemoryGuildPlaybackRepository(),
        player_factory=lambda _guild_id: FakeGuildPlayer(),
        playlist_service=PlaylistService(
            uow_factory=uow_factory,
            track_service=track_service,
        ),
        track_service=track_service,
        uow_factory=uow_factory,
    )
    return GuildPlaybackActorManager(actors=registry)


@pytest.mark.unit
class TestGuildLockCleanup:
    async def test_lock_entry_is_removed_after_execute_completes(self) -> None:
        manager: GuildPlaybackActorManager = _make_manager()

        with pytest.raises(PlaybackNotActiveError):
            await manager.execute(GetQueueCommand(guild_id=1, requested_by=1))

        assert manager._guild_locks == {}

    async def test_actor_execution_does_not_hold_lifecycle_lock(self) -> None:
        class BlockingActor:
            def __init__(self) -> None:
                self.submitted = asyncio.Event()
                self.result: asyncio.Future[GetQueueResult] | None = None

            def submit(self, command: GetQueueCommand) -> asyncio.Future[GetQueueResult]:
                self.result = asyncio.get_running_loop().create_future()
                self.submitted.set()
                return self.result

        class Registry:
            def __init__(self, actor: BlockingActor) -> None:
                self.actor = actor

            def get(self, *, guild_id: int) -> BlockingActor:
                return self.actor

        actor = BlockingActor()
        manager = GuildPlaybackActorManager(
            actors=cast(GuildPlaybackActorRegistry, Registry(actor))
        )
        command = GetQueueCommand(guild_id=1, requested_by=1)

        execution = asyncio.create_task(manager.execute(command))
        await asyncio.wait_for(actor.submitted.wait(), timeout=1)

        assert manager._guild_locks == {}
        assert actor.result is not None
        actor.result.set_result(GetQueueResult(tracks=()))
        await execution

    async def test_play_playlist_command_creates_missing_actor(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        class Actor:
            def submit(self, command: PlayPlaylistCommand) -> asyncio.Future[PlayPlaylistResult]:
                result: asyncio.Future[PlayPlaylistResult] = (
                    asyncio.get_running_loop().create_future()
                )
                result.set_result(
                    PlayPlaylistResult(
                        playlist_title="Playlist",
                        queued_count=1,
                        started_playing=True,
                    )
                )
                return result

        class Registry:
            def __init__(self) -> None:
                self.actor = Actor()
                self.created_guild_ids: list[int] = []

            def get(self, *, guild_id: int) -> None:
                return None

            async def create_or_restore(self, *, guild_id: int) -> Actor:
                self.created_guild_ids.append(guild_id)
                return self.actor

        registry = Registry()
        manager = GuildPlaybackActorManager(actors=cast(GuildPlaybackActorRegistry, registry))
        caplog.set_level(logging.DEBUG)

        result = await manager.execute(
            PlayPlaylistCommand(
                guild_id=1,
                requested_by=2,
                playlist_id="playlist-1",
            )
        )

        assert registry.created_guild_ids == [1]
        assert result.queued_count == 1
        messages: list[str] = [record.getMessage() for record in caplog.records]
        assert any("Playback use case started command=PlayPlaylistCommand" in m for m in messages)
        assert any("Playback use case completed command=PlayPlaylistCommand" in m for m in messages)

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
