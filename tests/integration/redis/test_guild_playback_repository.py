from __future__ import annotations

from datetime import UTC, datetime

import pytest
from redis.asyncio import Redis

from music_bot.adapters.outbound.redis import RedisGuildPlaybackRepository
from music_bot.domain.music.models import GuildPlayback, Queue, Track

GUILD_ID = 1001


def _make_playback() -> GuildPlayback:
    track = Track(
        url="https://example.com/a.mp3",
        title="Song A",
        requested_by=42,
        requested_at=datetime.now(UTC),
        duration_seconds=180,
    )
    return GuildPlayback(guild_id=GUILD_ID, queue=Queue((track,)), volume=80, loop_current=True)


@pytest.mark.integration
class TestRedisGuildPlaybackRepository:
    async def test_save_then_get_round_trips(self, redis_client: Redis) -> None:
        repo = RedisGuildPlaybackRepository(client=redis_client, ttl_seconds=60)
        playback: GuildPlayback = _make_playback()

        await repo.save(playback=playback)
        loaded: GuildPlayback | None = await repo.get(guild_id=GUILD_ID)

        assert loaded is not None
        assert loaded.guild_id == GUILD_ID
        assert loaded.volume == 80
        assert loaded.loop_current is True
        assert [t.title for t in loaded.tracks] == ["Song A"]
        assert loaded.tracks[0].requested_at == playback.tracks[0].requested_at

    async def test_get_missing_returns_none(self, redis_client: Redis) -> None:
        repo = RedisGuildPlaybackRepository(client=redis_client, ttl_seconds=60)

        assert await repo.get(guild_id=9999) is None

    async def test_delete_removes_saved_state(self, redis_client: Redis) -> None:
        repo = RedisGuildPlaybackRepository(client=redis_client, ttl_seconds=60)
        await repo.save(playback=_make_playback())

        await repo.delete(guild_id=GUILD_ID)

        assert await repo.get(guild_id=GUILD_ID) is None

    async def test_save_sets_ttl(self, redis_client: Redis) -> None:
        repo = RedisGuildPlaybackRepository(client=redis_client, ttl_seconds=60)
        await repo.save(playback=_make_playback())

        ttl: int = await redis_client.ttl(f"playback:{GUILD_ID}")

        assert 0 < ttl <= 60
