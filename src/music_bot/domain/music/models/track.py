from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class Track:
    url: str
    title: str
    requested_by: int
    duration_seconds: int
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.url:
            raise ValueError("url must not be empty")
        if not self.title:
            raise ValueError("title must not be empty")
        if self.requested_by <= 0:
            raise ValueError("requested_by must be positive")
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must not be negative")
