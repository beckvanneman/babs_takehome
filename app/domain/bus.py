"""Simple synchronous in-process event bus."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable


class EventBus:
    """Publish/subscribe bus for domain events.

    Handlers are called synchronously in registration order.
    """

    def __init__(self) -> None:
        self._subscribers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Callable) -> None:
        self._subscribers[event_type].append(handler)

    def publish(self, event: Any) -> None:
        for handler in self._subscribers.get(type(event), []):
            handler(event)
