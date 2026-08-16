from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from redis.asyncio import Redis

from music_bot.domain.music.models import GuildPlayback, Queue, Track


class RedisGuildPlaybackRepository:
    def __init__(
        self,
        *,
        client: Redis,
        ttl_seconds: int,
    ) -> None:
        self._client: Redis = client
        self._ttl_seconds: int = ttl_seconds

    async def get(self, *, guild_id: int) -> GuildPlayback | None:
        playback_key: str = self._playback_key(guild_id)
        raw: str | bytes | None = await self._client.get(playback_key)

        if raw is None:
            return None

        text: str = raw.decode() if isinstance(raw, bytes) else raw
        payload: dict[str, Any] = json.loads(text)

        return GuildPlayback(
            guild_id=guild_id,
            loop_current=payload["loop_current"],
            paused=payload["paused"],
            volume=payload["volume"],
            queue=Queue(
                Track(
                    url=track["url"],
                    title=track["title"],
                    duration_seconds=track["duration_seconds"],
                    requested_by=track["requested_by"],
                    requested_at=datetime.fromisoformat(track["requested_at"]),
                )
                for track in payload["queue"]
            ),
        )

    async def save(self, *, playback: GuildPlayback) -> None:
        playback_key: str = self._playback_key(playback.guild_id)

        payload: dict[str, Any] = {
            "loop_current": playback.loop_current,
            "paused": playback.is_paused,
            "volume": playback.volume,
            "queue": [
                {
                    "url": track.url,
                    "title": track.title,
                    "duration_seconds": track.duration_seconds,
                    "requested_by": track.requested_by,
                    "requested_at": track.requested_at.isoformat(),
                }
                for track in playback.tracks
            ],
        }

        await self._client.set(
            playback_key,
            json.dumps(payload),
            ex=self._ttl_seconds,
        )

    async def delete(self, *, guild_id: int) -> None:
        await self._client.delete(self._playback_key(guild_id))

    @staticmethod
    def _playback_key(guild_id: int) -> str:
        return f"playback:{guild_id}"
