from __future__ import annotations

from collections.abc import Iterable, Sequence
from random import Random

from .queue import Queue
from .track import Track


class GuildPlayback:
    def __init__(
        self,
        *,
        guild_id: int,
        queue: Queue | None = None,
        loop_current: bool = False,
        paused: bool = False,
        volume: int = 100,
    ) -> None:
        if guild_id <= 0:
            raise ValueError("guild_id must be positive")
        self._guild_id: int = guild_id
        self._queue: Queue = queue if queue is not None else Queue()
        self._loop_current: bool = loop_current
        self._paused: bool = paused
        self._volume: int = 100
        self.set_volume(volume)

    @property
    def guild_id(self) -> int:
        return self._guild_id

    @property
    def loop_current(self) -> bool:
        return self._loop_current

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def volume(self) -> int:
        return self._volume

    @property
    def tracks(self) -> Sequence[Track]:
        return self._queue.items

    @property
    def track_count(self) -> int:
        return len(self._queue)

    @property
    def current_track(self) -> Track | None:
        return self._queue.peek()

    @property
    def first_track(self) -> Track:
        track: Track | None = self.current_track
        if track is None:
            raise RuntimeError("GuildPlayback has no tracks")
        return track

    def enqueue(self, track: Track) -> None:
        self._queue.enqueue(track)

    def enqueue_many(self, tracks: Iterable[Track]) -> None:
        self._queue.enqueue_many(tracks)

    def clear(self) -> int:
        track_count: int = len(self._queue)
        self._queue.clear()
        self.disable_loop()
        self.resume()
        return track_count

    def skip(self) -> bool:
        self.disable_loop()
        self.resume()
        self._queue.dequeue()
        return bool(self._queue)

    def finish_first(self) -> bool:
        if not self._loop_current:
            self._queue.dequeue()

        return bool(self._queue)

    def shuffle(self, *, randomizer: Random | None = None) -> None:
        self._queue.shuffle(randomizer=randomizer)

    def enable_loop(self) -> None:
        self._loop_current = True

    def disable_loop(self) -> None:
        self._loop_current = False

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def set_volume(self, volume: int) -> None:
        if not 0 <= volume <= 100:
            raise ValueError("volume must be between 0 and 100")

        self._volume = volume
