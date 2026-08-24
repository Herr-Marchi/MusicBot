from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

type TrackFinishedCallback = Callable[[Exception | None], None]


@dataclass(frozen=True, slots=True)
class PlaybackSettings:
    volume: int
    is_paused: bool


type PlaybackSettingsProvider = Callable[[], PlaybackSettings]


class GuildPlayer(Protocol):
    async def play(
        self,
        *,
        url: str,
        settings: PlaybackSettingsProvider,
        on_finished: TrackFinishedCallback,
    ) -> None: ...

    async def stop(self) -> None: ...

    async def pause(self) -> None: ...

    async def resume(self) -> None: ...

    async def set_volume(self, volume: int) -> None: ...


type GuildPlayerFactory = Callable[[int], GuildPlayer]
