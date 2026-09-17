"""In-process asynchronous event bus and event definitions for Shyam."""

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel, Field

logger = logging.getLogger("shyam.events")


class Event(BaseModel):
    """Base model for all internal Shyam events."""

    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the event instance.",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when event occurred.",
    )

    @property
    def event_name(self) -> str:
        """Name of the event type."""
        return self.__class__.__name__

    model_config = {
        "frozen": True,
        "arbitrary_types_allowed": True,
    }


T = TypeVar("T", bound=Event)
EventHandler = Callable[[T], Coroutine[Any, Any, None]]


class EventBus:
    """Asynchronous in-process pub/sub event dispatcher."""

    def __init__(self) -> None:
        self._subscribers: dict[type[Event], list[EventHandler[Any]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, event_type: type[T], handler: EventHandler[T]) -> None:
        """Register an asynchronous subscriber for a specific event type."""
        async with self._lock:
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)

    async def unsubscribe(self, event_type: type[T], handler: EventHandler[T]) -> bool:
        """Unregister a subscriber for a specific event type. Returns True if removed."""
        async with self._lock:
            if handler in self._subscribers[event_type]:
                self._subscribers[event_type].remove(handler)
                return True
            return False

    async def publish(self, event: Event) -> None:
        """Publish an event to all registered subscribers concurrently."""
        event_type = type(event)
        async with self._lock:
            # Match exact type and superclasses (including base Event)
            handlers: list[EventHandler[Any]] = []
            for registered_type, registered_handlers in self._subscribers.items():
                if issubclass(event_type, registered_type):
                    handlers.extend(registered_handlers)

        if not handlers:
            return

        # Execute handlers concurrently, isolating exceptions
        tasks = [self._safe_invoke(handler, event) for handler in handlers]
        await asyncio.gather(*tasks)

    async def _safe_invoke(self, handler: EventHandler[Any], event: Event) -> None:
        """Safely invoke an event handler, preventing exceptions from propagating."""
        try:
            await handler(event)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Error in event handler %s for event %s: %s",
                handler,
                event.event_name,
                exc,
            )


# Standard core runtime events
class RuntimeStartedEvent(Event):
    """Fired when the runtime has completed initialization and is active."""

    runtime_id: str


class RuntimeStoppingEvent(Event):
    """Fired when runtime shutdown sequence begins."""

    runtime_id: str


class RuntimeStoppedEvent(Event):
    """Fired when runtime has completely halted."""

    runtime_id: str


class RuntimeErrorEvent(Event):
    """Fired when an unhandled runtime error occurs."""

    runtime_id: str
    error: str
