"""In-memory Capability Registry for local node capabilities."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from shyam.capabilities.events import (
    CapabilityRegisteredEvent,
    CapabilityUnregisteredEvent,
    CapabilityUpdatedEvent,
)
from shyam.capabilities.exceptions import (
    CapabilityNotFoundError,
    DuplicateCapabilityError,
)
from shyam.capabilities.model import AvailabilityStatus, Capability

if TYPE_CHECKING:
    from shyam.events.bus import EventBus

logger = logging.getLogger(__name__)


class CapabilityRegistry:
    """Manages the registration, lookup, and query of local capabilities.

    Maintains an in-memory registry of capabilities advertised by the local node.
    Optionally publishes domain events to an EventBus when state changes.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._capabilities: dict[str, Capability] = {}
        self._event_bus: EventBus | None = event_bus

    @property
    def count(self) -> int:
        """Return the count of currently registered capabilities."""
        return len(self._capabilities)

    def contains(self, capability_id: str) -> bool:
        """Check if a capability ID is registered."""
        return capability_id in self._capabilities

    def __contains__(self, capability_id: str) -> bool:
        return self.contains(capability_id)

    async def register(
        self,
        capability: Capability,
        *,
        overwrite: bool = False,
    ) -> None:
        """Register a new capability.

        Args:
            capability: The Capability model instance.
            overwrite: If True, replaces existing registration without error.

        Raises:
            DuplicateCapabilityError: If capability_id already exists and overwrite is False.
        """
        cap_id = capability.capability_id
        is_update = cap_id in self._capabilities

        if is_update and not overwrite:
            raise DuplicateCapabilityError(
                f"Capability '{cap_id}' is already registered. Set overwrite=True to update."
            )

        prev_cap = self._capabilities.get(cap_id)
        self._capabilities[cap_id] = capability

        logger.info(
            "%s capability: %s (v%s)",
            "Updated" if is_update else "Registered",
            cap_id,
            capability.version,
        )

        if self._event_bus:
            if is_update:
                prev_status = prev_cap.availability.value if prev_cap else None
                await self._event_bus.publish(
                    CapabilityUpdatedEvent(
                        capability_id=cap_id,
                        capability=capability,
                        previous_availability=prev_status,
                    )
                )
            else:
                await self._event_bus.publish(
                    CapabilityRegisteredEvent(
                        capability_id=cap_id,
                        capability=capability,
                    )
                )

    async def unregister(self, capability_id: str) -> Capability:
        """Remove a capability by its ID.

        Args:
            capability_id: Namespaced identifier of the capability.

        Returns:
            The removed Capability instance.

        Raises:
            CapabilityNotFoundError: If the capability is not registered.
        """
        if capability_id not in self._capabilities:
            raise CapabilityNotFoundError(
                f"Cannot unregister non-existent capability '{capability_id}'."
            )

        cap = self._capabilities.pop(capability_id)
        logger.info("Unregistered capability: %s", capability_id)

        if self._event_bus:
            await self._event_bus.publish(
                CapabilityUnregisteredEvent(capability_id=capability_id)
            )

        return cap

    def get(self, capability_id: str) -> Capability | None:
        """Retrieve a capability by ID, or None if not registered."""
        return self._capabilities.get(capability_id)

    def list_all(self) -> list[Capability]:
        """Return a list of all registered capabilities."""
        return list(self._capabilities.values())

    def find(
        self,
        *,
        namespace: str | None = None,
        availability: AvailabilityStatus | None = None,
    ) -> list[Capability]:
        """Query capabilities matching optional filter criteria.

        Args:
            namespace: Prefix match (e.g. 'file' matches 'file.read', 'file.write').
            availability: Filter by AvailabilityStatus.

        Returns:
            List of matching Capability instances.
        """
        results: list[Capability] = []
        for cap in self._capabilities.values():
            if namespace and not cap.capability_id.startswith(f"{namespace}."):
                continue
            if availability is not None and cap.availability != availability:
                continue
            results.append(cap)
        return results
