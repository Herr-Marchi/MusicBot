from __future__ import annotations

import logging

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger: logging.Logger = logging.getLogger(__name__)


def create_engine(*, database_url: str) -> AsyncEngine:
    url: URL = make_url(database_url)
    logger.info(
        "Creating Postgres engine driver=%s host=%r port=%s database=%r",
        url.drivername,
        url.host,
        url.port,
        url.database,
    )
    engine: AsyncEngine = create_async_engine(database_url)
    logger.debug("Postgres engine created")
    return engine


def create_session_factory(*, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    logger.debug("Postgres session factory created expire_on_commit=False")
    return factory
