"""In-memory Provider Registry for local node providers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from shyam.capabilities.model import AvailabilityStatus
from shyam.providers.events import (
    ProviderRegisteredEvent,
    ProviderUnregisteredEvent,
    ProviderUpdatedEvent,
)
from shyam.providers.exceptions import (
    DuplicateProviderError,
    ProviderNotFoundError,
)
from shyam.providers.model import Provider

if TYPE_CHECKING:
    from shyam.events.bus import EventBus

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Manages the registration, lookup, and query of local providers.

    Maintains an in-memory registry of providers advertised by the local node.
    Optionally publishes domain events to an EventBus when state changes.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._providers: dict[str, Provider] = {}
        self._event_bus: EventBus | None = event_bus

    @property
    def count(self) -> int:
        """Return the count of currently registered providers."""
        return len(self._providers)

    def contains(self, provider_id: str) -> bool:
        """Check if a provider ID is registered."""
        return provider_id in self._providers

    def __contains__(self, provider_id: str) -> bool:
        return self.contains(provider_id)

    async def register(
        self,
        provider: Provider,
        *,
        overwrite: bool = False,
    ) -> None:
        """Register a new provider.

        Args:
            provider: The Provider model instance.
            overwrite: If True, replaces existing registration without error.

        Raises:
            DuplicateProviderError: If provider_id already exists and overwrite is False.
        """
        prov_id = provider.provider_id
        is_update = prov_id in self._providers

        if is_update and not overwrite:
            raise DuplicateProviderError(
                f"Provider '{prov_id}' is already registered. Set overwrite=True to update."
            )

        prev_prov = self._providers.get(prov_id)
        self._providers[prov_id] = provider

        logger.info(
            "%s provider: %s (v%s)",
            "Updated" if is_update else "Registered",
            prov_id,
            provider.version,
        )

        if self._event_bus:
            if is_update:
                prev_status = prev_prov.availability.value if prev_prov else None
                await self._event_bus.publish(
                    ProviderUpdatedEvent(
                        provider_id=prov_id,
                        provider=provider,
                        previous_availability=prev_status,
                    )
                )
            else:
                await self._event_bus.publish(
                    ProviderRegisteredEvent(
                        provider_id=prov_id,
                        provider=provider,
                    )
                )

    async def unregister(self, provider_id: str) -> Provider:
        """Remove a provider by its ID.

        Args:
            provider_id: Namespaced identifier of the provider.

        Returns:
            The removed Provider instance.

        Raises:
            ProviderNotFoundError: If the provider is not registered.
        """
        if provider_id not in self._providers:
            raise ProviderNotFoundError(
                f"Cannot unregister non-existent provider '{provider_id}'."
            )

        prov = self._providers.pop(provider_id)
        logger.info("Unregistered provider: %s", provider_id)

        if self._event_bus:
            await self._event_bus.publish(
                ProviderUnregisteredEvent(provider_id=provider_id)
            )

        return prov

    def get(self, provider_id: str) -> Provider | None:
        """Retrieve a provider by ID, or None if not registered."""
        return self._providers.get(provider_id)

    def list_all(self) -> list[Provider]:
        """Return a list of all registered providers."""
        return list(self._providers.values())

    def find(
        self,
        *,
        namespace: str | None = None,
        availability: AvailabilityStatus | None = None,
    ) -> list[Provider]:
        """Query providers matching optional filter criteria.

        Args:
            namespace: Prefix match (e.g. 'local' matches 'local.filesystem', 'local.shell').
            availability: Filter by AvailabilityStatus.

        Returns:
            List of matching Provider instances.
        """
        results: list[Provider] = []
        for prov in self._providers.values():
            if namespace and not prov.provider_id.startswith(f"{namespace}."):
                continue
            if availability is not None and prov.availability != availability:
                continue
            results.append(prov)
        return results

    def find_by_capability(self, capability_id: str) -> list[Provider]:
        """Query providers that provide a given capability ID.

        Args:
            capability_id: Namespaced capability ID (e.g. 'file.read').

        Returns:
            List of Provider instances that list capability_id in their capabilities.
        """
        return [
            prov
            for prov in self._providers.values()
            if capability_id in prov.capabilities
        ]
