from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredTrack:
    id: str
    url: str
    title: str
    duration_seconds: int
