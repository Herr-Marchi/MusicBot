from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field

from music_bot.application.contracts.results.music import PlaybackResult


class PlaybackCommand[ResultT: PlaybackResult](BaseModel):
    guild_id: int = Field(..., gt=0)
    requested_by: int = Field(..., gt=0)

    # Whether the manager may spin up a new actor for this command when the
    # guild has none yet, instead of rejecting it. False for every command
    # unless a subclass explicitly opts in
    creates_actor: ClassVar[bool] = False
