from __future__ import annotations

from dataclasses import dataclass

from .base import PlaybackResult


@dataclass(frozen=True, slots=True)
class SetVolumeResult(PlaybackResult):
    volume: int
