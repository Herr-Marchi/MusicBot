from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SettingsLoadError(RuntimeError):
    message: str

    def __post_init__(self) -> None:
        super().__init__(self.message)
