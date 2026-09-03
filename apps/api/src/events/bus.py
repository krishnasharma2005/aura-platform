"""A minimal in-process pub/sub event bus. No Kafka/RabbitMQ needed at MVP
scale — subscribers are plain async callables registered at startup."""

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)

Subscriber = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscriber]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: Subscriber) -> None:
        self._subscribers[event_name].append(handler)

    async def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        handlers = self._subscribers.get(event_name, [])
        if not handlers:
            return
        results = await asyncio.gather(*(handler(payload) for handler in handlers), return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.error("event_handler_failed", exc_info=result, extra={"extra_fields": {"event": event_name}})


event_bus = EventBus()
