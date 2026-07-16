import math
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Hashable
from threading import Lock

from fastapi import HTTPException, status


class RateLimiter:
    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ):
        if limit <= 0 or window_seconds <= 0 or max_keys <= 0:
            raise ValueError("Rate limiter settings must be positive.")
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._clock = clock
        self._entries: OrderedDict[Hashable, deque[float]] = OrderedDict()
        self._lock = Lock()

    def check(self, key: Hashable) -> None:
        with self._lock:
            now = self._clock()
            self._remove_expired(now)
            timestamps = self._entries.get(key)

            if timestamps is None:
                if len(self._entries) >= self.max_keys:
                    self._entries.popitem(last=False)
                timestamps = deque()
                self._entries[key] = timestamps
            else:
                self._entries.move_to_end(key)

            if len(timestamps) >= self.limit:
                retry_after = max(
                    1,
                    math.ceil(timestamps[0] + self.window_seconds - now),
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests",
                    headers={"Retry-After": str(retry_after)},
                )

            timestamps.append(now)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    @property
    def key_count(self) -> int:
        with self._lock:
            return len(self._entries)

    def _remove_expired(self, now: float) -> None:
        cutoff = now - self.window_seconds
        for key, timestamps in list(self._entries.items()):
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if not timestamps:
                del self._entries[key]
