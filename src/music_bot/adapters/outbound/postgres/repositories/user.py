from __future__ import annotations

from sqlalchemy import ScalarResult
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.dml import ReturningInsert

from music_bot.adapters.outbound.postgres.models import DiscordUserModel
from music_bot.application.ports.playlists import DiscordUserData


class PostgresUserRepository:
    def __init__(self, *, session: AsyncSession) -> None:
        self._session: AsyncSession = session

    async def get(self, *, user_id: int) -> DiscordUserData | None:
        user: DiscordUserModel | None = await self._session.get(DiscordUserModel, user_id)
        if user is None:
            return None

        return self._to_data(user)

    async def upsert(self, *, user_id: int, username: str) -> DiscordUserData:
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

        return self._to_data(user)

    @staticmethod
    def _to_data(user: DiscordUserModel) -> DiscordUserData:
        return DiscordUserData(
            id=user.discord_user_id,
            username=user.username,
        )
