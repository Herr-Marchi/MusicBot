from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from .errors import SettingsLoadError
from .models import Settings


def load_settings() -> Settings:
    project_root: Path = Path(__file__).resolve().parents[4]
    dotenv_path: Path = project_root / ".env"

    load_dotenv(dotenv_path=dotenv_path, override=False)

    try:
        settings: Settings = Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        raise SettingsLoadError(f"Invalid environment configuration: {exc}") from exc

    return settings
