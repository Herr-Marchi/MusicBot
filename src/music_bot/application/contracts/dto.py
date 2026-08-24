from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class QueuedTrackDto:
    url: str
    title: str
    requested_by: int
    requested_at: datetime
    duration_seconds: int
