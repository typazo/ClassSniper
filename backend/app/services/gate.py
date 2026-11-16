"""Priority-aware Cornell API request gate protecting PollerEngine latency."""

from __future__ import annotations

import asyncio
import heapq
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Optional

PRIORITY_POLLER = 0
PRIORITY_SEARCH = 1
PRIORITY_WARMUP = 2


@dataclass(order=True)
class _Waiter:
    priority: int
    seq: int
    event: asyncio.Event = field(compare=False)
    cancelled: bool = field(default=False, compare=False)


class CornellRequestGate:
    """Coordinates outbound Cornell API calls so high-priority polling never waits on catalog sync."""

    def __init__(self) -> None:
        self._busy = False
        self._seq = 0
        self._waiters: list[_Waiter] = []
        self._last_catalog_mono: float = 0.0
        self._backoff_until_mono: float = 0.0
        self._poller_waiters: int = 0
        self._has_active_poller_fn: Optional[Callable[[], bool]] = None

    def set_active_poller_fn(self, fn: Optional[Callable[[], bool]]) -> None:
        self._has_active_poller_fn = fn

    def has_active_poller(self) -> bool:
        if self._poller_waiters > 0:
            return True
        if self._has_active_poller_fn is not None:
            return bool(self._has_active_poller_fn())
        return False

    def poller_is_pending(self) -> bool:
        return self._poller_waiters > 0

    def record_request_started(self, priority: int) -> None:
        if priority > PRIORITY_POLLER:
            self._last_catalog_mono = time.monotonic()

    def record_rate_limit(self, retry_after_sec: float) -> None:
        until = time.monotonic() + max(5.0, float(retry_after_sec))
        if until > self._backoff_until_mono:
            self._backoff_until_mono = until

    def clear_backoff(self) -> None:
        self._backoff_until_mono = 0.0

    def _wake_next(self) -> None:
        while self._waiters:
            nxt = heapq.heappop(self._waiters)
            if not nxt.cancelled:
                nxt.event.set()
                return
        self._busy = False

    async def _acquire(self, priority: int) -> None:
        if not self._busy:
            self._busy = True
            return
        self._seq += 1
        waiter = _Waiter(priority=priority, seq=self._seq, event=asyncio.Event())
        heapq.heappush(self._waiters, waiter)
        if priority == PRIORITY_POLLER:
            self._poller_waiters += 1
        try:
            await waiter.event.wait()
        except asyncio.CancelledError:
            waiter.cancelled = True
            # If ownership was just handed to us before cancellation landed, pass it along
            if waiter.event.is_set():
                self._wake_next()
            raise
        finally:
            if priority == PRIORITY_POLLER:
                self._poller_waiters = max(0, self._poller_waiters - 1)

    def _release(self) -> None:
        self._wake_next()

    @asynccontextmanager
    async def slot(
        self,
        priority: int = PRIORITY_SEARCH,
        min_interval_sec: float = 0.0,
        honor_backoff: bool = True,
    ) -> AsyncIterator[None]:
        """Acquire an exclusive Cornell request slot respecting priority and inter-request pacing."""
        while True:
            await self._acquire(priority)
            now = time.monotonic()
            # Catalog pacing tracks prior catalog requests so steady PollerEngine ticks cannot starve searches/warmup
            ready_at = self._last_catalog_mono + max(0.0, min_interval_sec)
            if honor_backoff:
                ready_at = max(ready_at, self._backoff_until_mono)
            # Lower-priority callers yield without holding the gate if pacing or backoff requires waiting
            if priority > PRIORITY_POLLER and ready_at > now:
                wait_for = min(ready_at - now, 10.0)
                self._release()
                await asyncio.sleep(wait_for)
                continue
            break

        try:
            self.record_request_started(priority)
            yield
        finally:
            self._release()
