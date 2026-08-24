from __future__ import annotations

import logging

from sqlalchemy import ScalarResult
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.dml import ReturningInsert

from music_bot.adapters.outbound.postgres.models import DiscordUserModel
from music_bot.application.ports.playlists import DiscordUserData

logger: logging.Logger = logging.getLogger(__name__)


class PostgresUserRepository:
    def __init__(self, *, session: AsyncSession) -> None:
        self._session: AsyncSession = session

    async def get(self, *, user_id: int) -> DiscordUserData | None:
        logger.debug("Postgres Discord user lookup started user_id=%s", user_id)
        user: DiscordUserModel | None = await self._session.get(DiscordUserModel, user_id)
        if user is None:
            logger.debug("Postgres Discord user lookup completed user_id=%s found=False", user_id)
            return None

        data: DiscordUserData = self._to_data(user)
        logger.debug("Postgres Discord user lookup completed user_id=%s found=True", user_id)
        return data

    async def upsert(self, *, user_id: int, username: str) -> DiscordUserData:
        logger.debug(
            "Postgres Discord user upsert started user_id=%s username_length=%s",
            user_id,
            len(username),
        )
        statement: ReturningInsert[tuple[DiscordUserModel]] = (
            insert(DiscordUserModel)
            .values(discord_user_id=user_id, username=username)
            .on_conflict_do_update(
                index_elements=[DiscordUserModel.discord_user_id],
                set_={"username": username},
            )
            .returning(DiscordUserModel)
        )
        result: ScalarResult[DiscordUserModel] = await self._session.scalars(statement)
        user: DiscordUserModel = result.one()

        data: DiscordUserData = self._to_data(user)
        logger.debug("Postgres Discord user upsert completed user_id=%s", user_id)
        return data

    @staticmethod
    def _to_data(user: DiscordUserModel) -> DiscordUserData:
        return DiscordUserData(
            id=user.discord_user_id,
            username=user.username,
        )
