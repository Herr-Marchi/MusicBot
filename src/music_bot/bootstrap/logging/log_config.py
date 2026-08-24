from __future__ import annotations

import logging

from rich.logging import RichHandler

from music_bot.bootstrap.settings import Settings
from music_bot.bootstrap.settings.types import LogLevel

_LEVEL_MAP: dict[str, int] = {
    LogLevel.DEBUG: logging.DEBUG,
    LogLevel.INFO: logging.INFO,
    LogLevel.WARNING: logging.WARNING,
    LogLevel.ERROR: logging.ERROR,
    LogLevel.CRITICAL: logging.CRITICAL,
}


def configure_logging(settings: Settings) -> None:
    level: int = _LEVEL_MAP[settings.log_level]

    handler: logging.Handler = RichHandler(
        rich_tracebacks=True,
        show_time=True,
        omit_repeated_times=True,
        log_time_format="[%H:%M:%S]",
        show_level=True,
        show_path=False,
    )
    handler.setLevel(logging.DEBUG)

    root_logger: logging.Logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    logging.getLogger("discord").setLevel(logging.INFO)
    logging.getLogger("aiohttp").setLevel(logging.INFO)

    logging.getLogger(__name__).debug(
        "Logging configured root_level=%s discord_level=INFO aiohttp_level=INFO",
        settings.log_level,
    )
