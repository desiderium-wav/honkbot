"""
Timing Utilities — Shared Scheduling Helpers

THIS MODULE DEFINES NO COMMANDS.

Provides reusable utilities for:
- Randomized delays
- Cooldowns
- Timed execution windows
- Background task scheduling helpers
"""

from __future__ import annotations

import asyncio
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Hashable, Optional, Tuple

Key = Hashable

def _now() -> float:
    """Return a monotonic timestamp in seconds."""
    return time.monotonic()

def remaining_time(start: float, duration: float, *, now: Optional[float] = None) -> float:
    """Return remaining time in a window, clamped to zero."""
    current = _now() if now is None else now
    return max(0.0, (start + duration) - current)

@dataclass
class TimedWindow:
    """Simple helper for checking fixed duration windows."""

    duration: float
    started_at: float = field(default_factory=_now)

    def remaining(self, *, now: Optional[float] = None) -> float:
        return remaining_time(self.started_at, self.duration, now=now)

    def expired(self, *, now: Optional[float] = None) -> bool:
        return self.remaining(now=now) <= 0.0

    def restart(self, *, now: Optional[float] = None) -> None:
        self.started_at = _now() if now is None else now

async def randomized_delay(min_seconds: float, max_seconds: float) -> float:
    """Sleep for a random duration between min_seconds and max_seconds.

    Returns the duration slept.
    """
    if min_seconds < 0 or max_seconds < 0:
        raise ValueError("Delay bounds must be non-negative")
    if max_seconds < min_seconds:
        raise ValueError("max_seconds must be >= min_seconds")
    duration = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(duration)
    return duration

def randomized_delay_value(min_seconds: float, max_seconds: float) -> float:
    """Return a randomized delay duration without sleeping."""
    if min_seconds < 0 or max_seconds < 0:
        raise ValueError("Delay bounds must be non-negative")
    if max_seconds < min_seconds:
        raise ValueError("max_seconds must be >= min_seconds")
    return random.uniform(min_seconds, max_seconds)

class CooldownTracker:
    """Track cooldowns per key using monotonic time."""

    def __init__(self, cooldown_seconds: float) -> None:
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be >= 0")
        self._cooldown_seconds = cooldown_seconds
        self._last_triggered: Dict[Key, float] = {}
        self._lock = asyncio.Lock()

    @property
    def cooldown_seconds(self) -> float:
        return self._cooldown_seconds

    async def remaining(self, key: Key) -> float:
        async with self._lock:
            last = self._last_triggered.get(key)
            if last is None:
                return 0.0
            return remaining_time(last, self._cooldown_seconds)

    async def ready(self, key: Key) -> bool:
        return await self.remaining(key) <= 0.0

    async def trigger(self, key: Key) -> None:
        async with self._lock:
            self._last_triggered[key] = _now()

    async def wait(self, key: Key) -> float:
        """Wait until the cooldown expires for the given key.

        Returns the waited duration.
        """
        delay = await self.remaining(key)
        if delay > 0:
            await asyncio.sleep(delay)
        return delay

    async def clear(self, key: Key) -> None:
        async with self._lock:
            self._last_triggered.pop(key, None)

    async def reset(self) -> None:
        async with self._lock:
            self._last_triggered.clear()

class RateLimiter:
    """Simple async-safe rate limiter using a sliding window."""

    def __init__(self, max_calls: int, per_seconds: float) -> None:
        if max_calls <= 0:
            raise ValueError("max_calls must be > 0")
        if per_seconds <= 0:
            raise ValueError("per_seconds must be > 0")
        self._max_calls = max_calls
        self._per_seconds = per_seconds
        self._timestamps: Deque[float] = deque()
        self._lock = asyncio.Lock()

    @property
    def max_calls(self) -> int:
        return self._max_calls

    @property
    def per_seconds(self) -> float:
        return self._per_seconds

    async def acquire(self) -> float:
        """Wait until a slot is available and reserve it.

        Returns the wait duration before the slot became available.
        """
        waited = 0.0
        while True:
            async with self._lock:
                now = _now()
                while self._timestamps and now - self._timestamps[0] >= self._per_seconds:
                    self._timestamps.popleft()
                if len(self._timestamps) < self._max_calls:
                    self._timestamps.append(now)
                    return waited
                next_available = self._per_seconds - (now - self._timestamps[0])
            waited += max(0.0, next_available)
            await asyncio.sleep(next_available)

    async def can_acquire(self) -> Tuple[bool, float]:
        """Return whether a slot is available and the wait time if not."""
        async with self._lock:
            now = _now()
            while self._timestamps and now - self._timestamps[0] >= self._per_seconds:
                self._timestamps.popleft()
            if len(self._timestamps) < self._max_calls:
                return True, 0.0
            wait = self._per_seconds - (now - self._timestamps[0])
            return False, max(0.0, wait)

    async def reset(self) -> None:
        async with self._lock:
            self._timestamps.clear()

async def rate_limit_check(
    limiter: RateLimiter,
) -> Tuple[bool, float]:
    """Return whether the limiter can acquire without waiting."""
    return await limiter.can_acquire()