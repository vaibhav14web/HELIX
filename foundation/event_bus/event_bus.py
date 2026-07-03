import asyncio
import uuid
from datetime import datetime, timezone
from typing import Callable, Coroutine, Any

from pydantic import BaseModel, Field


class HelixEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str
    event_type: str
    priority: int = 1
    payload: dict = Field(default_factory=dict)
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


EventHandler = Callable[[HelixEvent], Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        if event_type in self._subscribers:
            self._subscribers[event_type] = [h for h in self._subscribers[event_type] if h is not handler]

    async def publish(self, event: HelixEvent) -> None:
        handlers = self._subscribers.get(event.event_type, [])
        if not handlers:
            return
        sorted_handlers = sorted(handlers, key=lambda _: event.priority, reverse=True)
        await asyncio.gather(*[handler(event) for handler in sorted_handlers], return_exceptions=True)

    async def publish_event(self, source: str, event_type: str, payload: dict, priority: int = 1, correlation_id: str | None = None) -> HelixEvent:
        event = HelixEvent(
            source=source,
            event_type=event_type,
            priority=priority,
            payload=payload,
            correlation_id=correlation_id or str(uuid.uuid4()),
        )
        await self.publish(event)
        return event
