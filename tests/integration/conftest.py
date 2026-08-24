from __future__ import annotations

import os
import socket
import subprocess
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from urllib.parse import SplitResult, urlsplit

import pytest
from redis.asyncio import Redis
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from music_bot.adapters.outbound.postgres import (
    PostgresUoWFactory,
    create_engine,
    create_session_factory,
)
from music_bot.adapters.outbound.redis import create_redis_client

REPO_ROOT: Path = Path(__file__).resolve().parents[2]

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://musicbot:musicbot@localhost:5432/musicbot"
)
REDIS_URL: str = os.environ.get("INTEGRATION_REDIS_URL", "redis://localhost:6379/15")


def _require_tcp_service(*, host: str, port: int, name: str) -> None:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            pass
    except OSError as exc:
        pytest.skip(f"{name} integration service is unavailable at {host}:{port}: {exc}")


@pytest.fixture(scope="session")
def _postgres_migrated() -> None:
    database_url: URL = make_url(DATABASE_URL)
    _require_tcp_service(
        host=database_url.host or "localhost",
        port=database_url.port or 5432,
        name="Postgres",
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": DATABASE_URL},
    )


@pytest.fixture(scope="session")
async def postgres_engine(_postgres_migrated: None) -> AsyncGenerator[AsyncEngine]:
    engine: AsyncEngine = create_engine(database_url=DATABASE_URL)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def postgres_session_factory(
    postgres_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine=postgres_engine)


@pytest.fixture
def postgres_uow_factory(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> PostgresUoWFactory:
    return PostgresUoWFactory(session_factory=postgres_session_factory)


@pytest.fixture
async def redis_client() -> AsyncGenerator[Redis]:
    redis_url: SplitResult = urlsplit(REDIS_URL)
    _require_tcp_service(
        host=redis_url.hostname or "localhost",
        port=redis_url.port or 6379,
        name="Redis",
    )
    client: Redis = create_redis_client(database_url=REDIS_URL)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()
