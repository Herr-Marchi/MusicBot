from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

type TrackFinishedCallback = Callable[[Exception | None], None]


class GuildPlayer(Protocol):
    async def play(
        self,
        *,
        url: str,
        volume: int,
        on_finished: TrackFinishedCallback,
    ) -> None: ...

    async def stop(self) -> None: ...

    async def pause(self) -> None: ...

    async def resume(self) -> None: ...

    async def set_volume(self, volume: int) -> None: ...


type GuildPlayerFactory = Callable[[int], GuildPlayer]
