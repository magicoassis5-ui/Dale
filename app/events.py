from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Set

logger = logging.getLogger(__name__)


class EventBus:
    """Tiny in-process pub/sub. Each subscriber gets its own asyncio.Queue."""

    def __init__(self) -> None:
        self._subs: Set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1024)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, event: dict[str, Any]) -> None:
        # serialize once, ignore overflow per-subscriber
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("ws subscriber queue full, dropping event")


bus = EventBus()


def emit(kind: str, **payload: Any) -> None:
    bus.publish({"type": kind, **payload})
