from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Protocol

import pytest
from tests.fakes import FakeGuildPlayer, FakeTrackSource

from music_bot.adapters.outbound.in_memory.music import InMemoryGuildPlaybackRepository
from music_bot.application.orchestration.music.guild_playback_actor import GuildPlaybackActor
from music_bot.domain.music.models import GuildPlayback


class MakeActor(Protocol):
    def __call__(
        self,
        *,
        guild_id: int = 1,
        playback: GuildPlayback | None = None,
    ) -> GuildPlaybackActor: ...


@pytest.fixture
def fake_player() -> FakeGuildPlayer:
    return FakeGuildPlayer()


@pytest.fixture
def playback_repository() -> InMemoryGuildPlaybackRepository:
    return InMemoryGuildPlaybackRepository()


@pytest.fixture
def terminated_guild_ids() -> list[int]:
    return []


@pytest.fixture
def make_actor(
    fake_player: FakeGuildPlayer,
    fake_track_source: FakeTrackSource,
    playback_repository: InMemoryGuildPlaybackRepository,
    terminated_guild_ids: list[int],
) -> MakeActor:
    def _make_actor(
        *,
        guild_id: int = 1,
        playback: GuildPlayback | None = None,
    ) -> GuildPlaybackActor:
        def _terminated_callback(actor: GuildPlaybackActor) -> None:
            terminated_guild_ids.append(actor.guild_id)

        return GuildPlaybackActor(
            guild_id=guild_id,
            playback=playback,
            playback_repository=playback_repository,
            player=fake_player,
            metadata_resolver=fake_track_source,
            terminated_callback=_terminated_callback,
        )

    return _make_actor


@pytest.fixture
async def running_actor(make_actor: MakeActor) -> AsyncGenerator[GuildPlaybackActor]:
    actor: GuildPlaybackActor = make_actor()
    actor.start()
    yield actor
    await actor.close()
