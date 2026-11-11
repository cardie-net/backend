"""In-process sliding-window rate limiting shared by uploads and auth."""

import time
from collections import deque
from typing import Hashable

from fastapi import HTTPException, status

DEFAULT_WINDOW_SECONDS = 60
# Bounds the in-process map; stale entries are pruned past this size.
DEFAULT_MAX_KEYS = 10_000


class SlidingWindowLimiter:
    """In-process sliding-window limiter keyed by an arbitrary identifier.

    State lives in the worker process, so it is a backstop against abusive
    clients rather than an exact cluster-wide quota.
    """

    def __init__(
        self,
        detail: str,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        max_keys: int = DEFAULT_MAX_KEYS,
    ) -> None:
        self._detail = detail
        self.window_seconds = window_seconds
        self._max_keys = max_keys
        self._windows: dict[Hashable, deque[float]] = {}

    def check(self, key: Hashable, limit: int) -> None:
        """Record an attempt for key, raising 429 once limit is reached."""
        if limit <= 0:
            return

        now = time.monotonic()
        window = self._windows.setdefault(key, deque())
        while window and now - window[0] >= self.window_seconds:
            window.popleft()

        if len(window) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=self._detail,
                headers={"Retry-After": str(self.window_seconds)},
            )

        window.append(now)
        if len(self._windows) > self._max_keys:
            self._prune(now)

    def reset(self) -> None:
        """Forget every recorded attempt."""
        self._windows.clear()

    def _prune(self, now: float) -> None:
        stale = [
            key
            for key, window in self._windows.items()
            if not window or now - window[-1] >= self.window_seconds
        ]
        for key in stale:
            self._windows.pop(key, None)
