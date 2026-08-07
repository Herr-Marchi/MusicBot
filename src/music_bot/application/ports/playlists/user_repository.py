from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True, kw_only=True)
class DiscordUserData:
    id: int
    username: str


class UserRepository(Protocol):
    async def get(self, *, user_id: int) -> DiscordUserData | None: ...

    async def upsert(self, *, user_id: int, username: str) -> DiscordUserData: ...
