from __future__ import annotations

import asyncio

from music_bot.bootstrap import Container
from music_bot.bootstrap.logging import configure_logging
from music_bot.bootstrap.settings import Settings, SettingsLoadError, load_settings


async def main() -> None:
    try:
        settings: Settings = load_settings()
    except SettingsLoadError as exc:
        raise SystemExit(str(exc)) from exc

    configure_logging(settings)

    container: Container = Container.create(settings=settings)
    try:
        await container.start()
    finally:
        await container.close()


if __name__ == "__main__":
    asyncio.run(main())
