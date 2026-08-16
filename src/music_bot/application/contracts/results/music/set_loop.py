from __future__ import annotations

from dataclasses import dataclass

from .base import PlaybackResult


@dataclass(frozen=True, slots=True)
class SetLoopResult(PlaybackResult):
    enabled: bool
