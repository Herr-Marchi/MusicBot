from __future__ import annotations

import logging
from urllib.parse import urlsplit

from redis.asyncio import Redis

logger: logging.Logger = logging.getLogger(__name__)


def create_redis_client(*, database_url: str) -> Redis:
    parsed = urlsplit(database_url)
    logger.info(
        "Creating Redis client scheme=%s host=%r port=%s database=%r",
        parsed.scheme,
        parsed.hostname,
        parsed.port,
        parsed.path.lstrip("/") or "0",
    )
    client: Redis = Redis.from_url(database_url, decode_responses=True)
    logger.debug("Redis client created decode_responses=True")
    return client
