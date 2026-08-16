from __future__ import annotations

import logging

from music_bot.application.orchestration.music.events import TrackFinishedEvent
from music_bot.domain.music.models import GuildPlayback

logger: logging.Logger = logging.getLogger(__name__)


class TrackFinishedEventListener:
    def __init__(self, *, playback: GuildPlayback) -> None:
        self._playback: GuildPlayback = playback

    def handle(self, event: TrackFinishedEvent) -> bool:
        if event.exception is not None:
            logger.warning(
                "Track playback failed in guild %s: %s",
                self._playback.guild_id,
                event.exception,
            )
            self._playback.disable_loop()

        return self._playback.finish_first()
