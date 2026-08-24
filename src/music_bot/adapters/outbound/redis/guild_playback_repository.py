from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from redis.asyncio import Redis

from music_bot.domain.music.models import GuildPlayback, Queue, Track

logger: logging.Logger = logging.getLogger(__name__)


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
        logger.debug("Redis playback GET started guild_id=%s key=%s", guild_id, playback_key)
        raw: str | bytes | None = await self._client.get(playback_key)

        if raw is None:
            logger.info("Redis playback GET completed guild_id=%s found=False", guild_id)
            return None

        text: str = raw.decode() if isinstance(raw, bytes) else raw
        payload: dict[str, Any] = json.loads(text)

        playback = GuildPlayback(
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
        logger.info(
            "Redis playback GET completed guild_id=%s found=True queue_size=%s "
            "paused=%s volume=%s loop=%s",
            guild_id,
            playback.track_count,
            playback.is_paused,
            playback.volume,
            playback.loop_current,
        )
        return playback

    async def save(self, *, playback: GuildPlayback) -> None:
        playback_key: str = self._playback_key(playback.guild_id)
        logger.debug(
            "Redis playback SET started guild_id=%s key=%s queue_size=%s ttl_seconds=%s "
            "paused=%s volume=%s loop=%s",
            playback.guild_id,
            playback_key,
            playback.track_count,
            self._ttl_seconds,
            playback.is_paused,
            playback.volume,
            playback.loop_current,
        )

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
        logger.info(
            "Redis playback SET completed guild_id=%s queue_size=%s ttl_seconds=%s",
            playback.guild_id,
            playback.track_count,
            self._ttl_seconds,
        )

    async def delete(self, *, guild_id: int) -> None:
        playback_key: str = self._playback_key(guild_id)
        logger.debug("Redis playback DELETE started guild_id=%s key=%s", guild_id, playback_key)
        deleted: int = await self._client.delete(playback_key)
        logger.info("Redis playback DELETE completed guild_id=%s deleted=%s", guild_id, deleted)

    @staticmethod
    def _playback_key(guild_id: int) -> str:
        return f"playback:{guild_id}"
