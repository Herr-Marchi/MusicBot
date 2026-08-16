from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from music_bot.application.contracts.results.music import PlayPlaylistResult

from .base import PlaybackCommand


class PlayPlaylistCommand(PlaybackCommand[PlayPlaylistResult]):
    urls: list[str] = Field(..., min_length=1)

    creates_actor: ClassVar[bool] = True
