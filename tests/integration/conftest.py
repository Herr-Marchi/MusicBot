from __future__ import annotations

import os
import subprocess
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from music_bot.adapters.outbound.postgres import (
    PostgresPlaylistUoWFactory,
    create_engine,
    create_session_factory,
)
from music_bot.adapters.outbound.redis import create_redis_client

REPO_ROOT: Path = Path(__file__).resolve().parents[2]

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://musicbot:musicbot@localhost:5432/musicbot"
)
REDIS_URL: str = os.environ.get("INTEGRATION_REDIS_URL", "redis://localhost:6379/15")


@pytest.fixture(scope="session", autouse=True)
def _run_migrations() -> None:
    subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True,
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": DATABASE_URL},
    )


@pytest.fixture(scope="session")
async def postgres_engine() -> AsyncGenerator[AsyncEngine]:
    engine: AsyncEngine = create_engine(database_url=DATABASE_URL)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def postgres_session_factory(
    postgres_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine=postgres_engine)


@pytest.fixture
def playlist_uow_factory(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> PostgresPlaylistUoWFactory:
    return PostgresPlaylistUoWFactory(session_factory=postgres_session_factory)


@pytest.fixture
async def redis_client() -> AsyncGenerator[Redis]:
    client: Redis = create_redis_client(database_url=REDIS_URL)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()
