from __future__ import annotations

from redis.asyncio import Redis


def create_redis_client(*, database_url: str) -> Redis:
    return Redis.from_url(database_url, decode_responses=True)
