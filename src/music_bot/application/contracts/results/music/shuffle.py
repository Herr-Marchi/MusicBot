from __future__ import annotations

from dataclasses import dataclass

from .base import PlaybackResult


@dataclass(frozen=True, slots=True)
class ShuffleResult(PlaybackResult):
    shuffled: bool
    queue_size: int
