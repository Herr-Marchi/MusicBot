from __future__ import annotations

from typing import ClassVar

from music_bot.adapters.outbound.yt_dlp.base import YtDlpTrackSource


class SoundCloudTrackSource(YtDlpTrackSource):
    SOURCE_HOSTS: ClassVar[frozenset[str]] = frozenset(
        {
            "soundcloud.com",
            "www.soundcloud.com",
            "m.soundcloud.com",
            "on.soundcloud.com",
        }
    )
    STREAM_HOST_SUFFIXES: ClassVar[frozenset[str]] = frozenset(
        {"sndcdn.com", "soundcloud.com", "soundcloud.cloud"}
    )
