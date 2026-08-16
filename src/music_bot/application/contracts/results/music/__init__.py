from __future__ import annotations

from .base import PlaybackResult
from .get_queue import GetQueueResult
from .now_playing import NowPlayingResult
from .pause import PauseResult
from .play_playlist import PlayPlaylistResult
from .play_url import PlayUrlResult
from .resume import ResumeResult
from .set_loop import SetLoopResult
from .set_volume import SetVolumeResult
from .shuffle import ShuffleResult
from .skip import SkipResult
from .stop import StopResult

__all__ = (
    "GetQueueResult",
    "NowPlayingResult",
    "PauseResult",
    "PlayPlaylistResult",
    "PlayUrlResult",
    "PlaybackResult",
    "ResumeResult",
    "SetLoopResult",
    "SetVolumeResult",
    "ShuffleResult",
    "SkipResult",
    "StopResult",
)
