from __future__ import annotations

from typing import Protocol

from music_bot.application.contracts.commands.music import (
    NowPlayingCommand,
    PlayUrlCommand,
    SkipCommand,
    StopCommand,
)
from music_bot.domain.music.models import Track


class MakeTrack(Protocol):
    def __call__(self, url: str = "https://example.com/a.mp3", requested_by: int = 1) -> Track: ...


class MakePlayUrlCommand(Protocol):
    def __call__(
        self,
        guild_id: int = 1,
        url: str = "https://example.com/a.mp3",
        requested_by: int = 1,
    ) -> PlayUrlCommand: ...


class MakeStopCommand(Protocol):
    def __call__(self, guild_id: int = 1, requested_by: int = 1) -> StopCommand: ...


class MakeSkipCommand(Protocol):
    def __call__(self, guild_id: int = 1, requested_by: int = 1) -> SkipCommand: ...


class MakeNowPlayingCommand(Protocol):
    def __call__(self, guild_id: int = 1, requested_by: int = 1) -> NowPlayingCommand: ...
