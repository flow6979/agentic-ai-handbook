"""Tools ke liye chhota HTTP layer: timeout, retry, TTL cache, user-agent, trimming.

Agent ke tools internet pe jaate hain, aur internet unreliable hai. Isliye har API call:
  - timeout ke saath (warna agent hang ho jayega)
  - 429 / 5xx / network error pe retry (backoff ke saath)
  - cache ke saath (same sawaal -> same API call dobara nahi; paisa + latency bachta hai)
  - response ko trim karke (LLM ka context window chhota aur mehenga hai)
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable

import httpx

USER_AGENT = "agentic-ai-handbook/0.1 (learning project; https://github.com/flow6979/agentic-ai-handbook)"


class ApiError(Exception):
    """API call fail hui. Agent loop isko 'ERROR: ...' string bana ke LLM ko bhej dega."""


class TTLCache:
    """Simple in-memory cache: har entry `ttl` seconds tak valid rehti hai."""

    def __init__(self, ttl: float = 300.0, max_items: int = 256, clock: Callable[[], float] = time.monotonic):
        self.ttl = ttl
        self.max_items = max_items
        self._clock = clock
        self._data: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires_at, value = item
        if self._clock() > expires_at:
            del self._data[key]  # expire ho gaya
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        if len(self._data) >= self.max_items:  # sabse purani entry nikaalo (insertion order)
            self._data.pop(next(iter(self._data)))
        self._data[key] = (self._clock() + self.ttl, value)


class ApiClient:
    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        cache: TTLCache | None = None,
        retries: int = 2,
        timeout: float = 10.0,
        backoff: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.client = client or httpx.Client(
            timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        )
        self.client.headers.setdefault("User-Agent", USER_AGENT)
        self.cache = cache if cache is not None else TTLCache()
        self.retries = retries
        self.backoff = backoff
        self._sleep = sleep
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0}

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        key = url + "?" + json.dumps(params or {}, sort_keys=True)
        cached = self.cache.get(key)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return cached

        last_error = ""
        for attempt in range(self.retries + 1):
            if attempt:
                self.stats["retries"] += 1
                self._sleep(self.backoff * (2 ** (attempt - 1)))
            self.stats["requests"] += 1
            try:
                r = self.client.get(url, params=params)
            except httpx.TransportError as e:  # timeout, DNS, connection reset
                last_error = f"network error: {type(e).__name__}: {e}"
                continue
            if r.status_code == 429 or r.status_code >= 500:
                last_error = f"HTTP {r.status_code} (temporary)"
                continue
            if r.status_code >= 400:  # 400/404: retry se kuch nahi badlega
                raise ApiError(f"HTTP {r.status_code} from {url}: {r.text[:200]}")
            data = r.json()
            self.cache.set(key, data)
            return data
        raise ApiError(f"{url} failed after {self.retries + 1} attempts: {last_error}")


def trim(text: str, max_chars: int = 1500) -> str:
    """LLM ko poora dump mat bhejo. Lamba text kaato aur batao ki kaata gaya."""
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + f" ...[trimmed, {len(text) - max_chars} more chars]"
