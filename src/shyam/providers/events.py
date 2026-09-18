"""Domain events for the Shyam Provider subsystem."""

from __future__ import annotations

from pydantic import Field

from shyam.events.bus import Event
from shyam.providers.model import Provider


class ProviderRegisteredEvent(Event):
    """Published when a new provider is registered."""

    provider_id: str = Field(description="Unique namespaced provider ID")
    provider: Provider = Field(description="Full provider specification")


class ProviderUpdatedEvent(Event):
    """Published when an existing provider specification or status is updated."""

    provider_id: str = Field(description="Unique namespaced provider ID")
    provider: Provider = Field(description="Updated provider specification")
    previous_availability: str | None = Field(
        default=None,
        description="Availability status prior to update",
    )


class ProviderUnregisteredEvent(Event):
    """Published when a provider is removed from the registry."""

    provider_id: str = Field(description="ID of unregistered provider")
