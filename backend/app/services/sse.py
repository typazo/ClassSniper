"""In-memory Server-Sent Events pub/sub hub for live dashboard updates."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from dataclasses import dataclass


@dataclass(slots=True)
class _Subscriber:
    user_id: int
    is_admin: bool
    queue: asyncio.Queue[dict[str, Any]]


class SSEHub:
    """Fan-out hub delivering real-time status and telemetry events to connected browsers."""

    def __init__(self, max_queue_size: int = 100) -> None:
        self._subscribers: set[_Subscriber] = set()
        self._max_queue_size = max_queue_size

    @asynccontextmanager
    async def subscribe(self, user_id: int, is_admin: bool = False) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        sub = _Subscriber(
            user_id=user_id,
            is_admin=is_admin,
            queue=asyncio.Queue(maxsize=self._max_queue_size),
        )
        self._subscribers.add(sub)
        try:
            yield sub.queue
        finally:
            self._subscribers.discard(sub)

    def publish(self, event_type: str, data: dict[str, Any], user_ids: set[int] | None = None) -> None:
        """Push an event without blocking; drops oldest message if a client is stalled."""
        message = {"event": event_type, "data": data}
        for sub in list(self._subscribers):
            if user_ids is not None and sub.user_id not in user_ids and not sub.is_admin:
                continue
            if sub.queue.full():
                try:
                    sub.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                sub.queue.put_nowait(message)
            except asyncio.QueueFull:
                pass
