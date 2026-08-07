from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .mixins import TimestampMixin


class DiscordUserModel(TimestampMixin, Base):
    __tablename__ = "discord_users"

    discord_user_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )
    username: Mapped[str] = mapped_column(String(32))
