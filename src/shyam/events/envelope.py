"""Transport-neutral event envelope for distributed boundaries."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from shyam.events.bus import Event


class EventEnvelope[T: Event](BaseModel):
    """Transport-neutral container for events passing through the system."""

    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this envelope instance.",
    )
    event_type: str = Field(
        description="Dot-separated string or class name representing the event type.",
    )
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the event occurred.",
    )
    payload: T = Field(
        description="The actual domain event payload.",
    )
    source_node_id: str | None = Field(
        default=None,
        description="The persistent Node ID of the node that generated this event.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional transport or routing metadata.",
    )

    model_config = {
        "frozen": True,
    }

    @classmethod
    def wrap(
        cls,
        event: T,
        source_node_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "EventEnvelope[T]":
        """Wrap a raw Event into an EventEnvelope."""
        return cls(
            event_id=event.event_id,
            event_type=event.event_name,
            occurred_at=event.timestamp,
            payload=event,
            source_node_id=source_node_id,
            metadata=metadata or {},
        )
