from __future__ import annotations

import random
from collections import deque
from collections.abc import Iterable, Iterator, Sequence
from random import Random

from .track import Track


class Queue:
    def __init__(self, items: Iterable[Track] = ()) -> None:
        self._items: deque[Track] = deque(items)

    def __repr__(self) -> str:
        return f"<Queue: {len(self._items)} tracks>"

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    def __iter__(self) -> Iterator[Track]:
        return iter(self._items)

    @property
    def items(self) -> Sequence[Track]:
        return tuple(self._items)

    def enqueue(self, track: Track) -> None:
        self._items.append(track)

    def enqueue_many(self, tracks: Iterable[Track]) -> None:
        self._items.extend(tracks)

    def dequeue(self) -> Track | None:
        try:
            return self._items.popleft()
        except IndexError:
            return None

    def peek(self) -> Track | None:
        try:
            return self._items[0]
        except IndexError:
            return None

    def clear(self) -> None:
        self._items.clear()

    def shuffle(self, *, randomizer: Random | None = None) -> None:
        items: list[Track] = list(self._items)
        if randomizer is None:
            random.shuffle(items)
        else:
            randomizer.shuffle(items)

        self._items = deque(items)
