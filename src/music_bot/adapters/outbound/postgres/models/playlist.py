from __future__ import annotations

from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from music_bot.domain.playlists.models import PlaylistAccess

from .base import Base
from .mixins import TimestampMixin


class PlaylistModel(TimestampMixin, Base):
    __tablename__ = "playlists"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "title",
            name="uq_playlists_owner_id_title",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    title: Mapped[str] = mapped_column(String(100))
    owner_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("discord_users.discord_user_id", ondelete="RESTRICT"),
    )
    access: Mapped[PlaylistAccess] = mapped_column(SQLEnum(PlaylistAccess))
