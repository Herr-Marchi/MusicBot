from __future__ import annotations

from pydantic import Field

from music_bot.application.contracts.results.music import SetVolumeResult

from .base import PlaybackCommand


class SetVolumeCommand(PlaybackCommand[SetVolumeResult]):
    volume: int = Field(..., ge=0, le=100)
