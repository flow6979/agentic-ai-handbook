"""Per-user rate limiting (sliding window).

Kyun? Har request = paisa (tokens). Ek buggy client ya abuser loop mein hit kare to
bill phat jaata hai aur provider ka rate limit baaki users ke liye bhi khatam.
Production mein yeh Redis mein hota hai (multiple servers share karein); yahan in-memory.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float = 60.0, clock=time.monotonic):
        self.limit = limit
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] >= self.window_s:  # window se bahar wale hits hatao
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def retry_after(self, key: str) -> float:
        q = self._hits.get(key)
        if not q:
            return 0.0
        return max(0.0, self.window_s - (self._clock() - q[0]))
