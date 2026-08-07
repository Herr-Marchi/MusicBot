from __future__ import annotations

from uuid import UUID

from sqlalchemy import Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .mixins import TimestampMixin


class TrackModel(TimestampMixin, Base):
    __tablename__ = "tracks"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(String(512))
    duration_seconds: Mapped[int] = mapped_column(Integer)
