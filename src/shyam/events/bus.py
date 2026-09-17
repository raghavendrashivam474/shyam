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
EventHandler = Callable[[Any], Coroutine[Any, Any, None]]


class EventBus:
    """Asynchronous in-process pub/sub event dispatcher with Envelope awareness."""

    def __init__(self) -> None:
        self._subscribers: dict[type, list[EventHandler]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, event_type: type, handler: EventHandler) -> None:
        """Register an asynchronous subscriber for a specific event or envelope type."""
        async with self._lock:
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)

    async def unsubscribe(self, event_type: type, handler: EventHandler) -> bool:
        """Unregister a subscriber for a specific event type. Returns True if removed."""
        async with self._lock:
            if handler in self._subscribers[event_type]:
                self._subscribers[event_type].remove(handler)
                return True
            return False

    async def publish(self, event_or_envelope: Any) -> None:
        """Publish an event or envelope to all registered subscribers concurrently."""
        from shyam.events.envelope import EventEnvelope

        handlers_to_invoke: list[tuple[EventHandler, Any]] = []

        async with self._lock:
            if isinstance(event_or_envelope, EventEnvelope):
                # 1. Dispatch envelope to subscribers of EventEnvelope
                for registered_type, handlers in self._subscribers.items():
                    if registered_type is EventEnvelope or (
                        isinstance(registered_type, type)
                        and issubclass(registered_type, EventEnvelope)
                    ):
                        for h in handlers:
                            handlers_to_invoke.append((h, event_or_envelope))

                # 2. Dispatch the inner payload to subscribers of that Event type
                inner_event = event_or_envelope.payload
                inner_event_type = type(inner_event)
                for registered_type, handlers in self._subscribers.items():
                    if isinstance(registered_type, type) and issubclass(
                        inner_event_type, registered_type
                    ):
                        for h in handlers:
                            handlers_to_invoke.append((h, inner_event))
            else:
                # Direct Event published
                event_type = type(event_or_envelope)
                # 1. Dispatch direct event to its subscribers
                for registered_type, handlers in self._subscribers.items():
                    if isinstance(registered_type, type) and issubclass(
                        event_type, registered_type
                    ):
                        for h in handlers:
                            handlers_to_invoke.append((h, event_or_envelope))

                # 2. Automatically wrap in an EventEnvelope and dispatch to Envelope subscribers
                wrapped_envelope = EventEnvelope.wrap(event_or_envelope)
                for registered_type, handlers in self._subscribers.items():
                    if registered_type is EventEnvelope or (
                        isinstance(registered_type, type)
                        and issubclass(registered_type, EventEnvelope)
                    ):
                        for h in handlers:
                            handlers_to_invoke.append((h, wrapped_envelope))

        if not handlers_to_invoke:
            return

        # Execute handlers concurrently, isolating exceptions
        tasks = [self._safe_invoke(handler, msg) for handler, msg in handlers_to_invoke]
        await asyncio.gather(*tasks)

    async def _safe_invoke(self, handler: EventHandler, msg: Any) -> None:
        """Safely invoke an event handler, preventing exceptions from propagating."""
        try:
            await handler(msg)
        except Exception as exc:  # noqa: BLE001
            name = getattr(msg, "event_name", type(msg).__name__)
            logger.exception(
                "Error in event handler %s for message %s: %s",
                handler,
                name,
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
