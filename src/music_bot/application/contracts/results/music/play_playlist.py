from __future__ import annotations

from dataclasses import dataclass

from .base import PlaybackResult


@dataclass(frozen=True, slots=True)
class PlayPlaylistResult(PlaybackResult):
    playlist_title: str
    queued_count: int
    started_playing: bool
