"""Domain events for the Shyam Capability subsystem."""

from __future__ import annotations

from pydantic import Field

from shyam.capabilities.model import Capability
from shyam.events.bus import Event


class CapabilityRegisteredEvent(Event):
    """Published when a new capability is registered."""

    capability_id: str = Field(description="Unique namespaced capability ID")
    capability: Capability = Field(description="Full capability specification")


class CapabilityUpdatedEvent(Event):
    """Published when an existing capability specification or status is updated."""

    capability_id: str = Field(description="Unique namespaced capability ID")
    capability: Capability = Field(description="Updated capability specification")
    previous_availability: str | None = Field(
        default=None,
        description="Availability status prior to update",
    )


class CapabilityUnregisteredEvent(Event):
    """Published when a capability is removed from the registry."""

    capability_id: str = Field(description="ID of unregistered capability")
