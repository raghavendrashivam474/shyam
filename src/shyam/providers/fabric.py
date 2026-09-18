"""Shyam Local Provider Fabric - S5.

Manages the lifecycle, construction, validation, and registration
of concrete local providers on the current Shyam node.

The fabric is NOT an execution engine, navigator, or plugin loader.
It constructs known local providers, ensures their explicitly
declared capabilities are registered, and manages availability state.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from shyam.capabilities.model import AvailabilityStatus
from shyam.providers.base import LocalProvider
from shyam.providers.local.filesystem import LocalFilesystemProvider

logger = logging.getLogger("shyam.providers.fabric")


class LocalProviderFabric:
    """Orchestrates construction, lifecycle, and registration of local providers.

    Coordinates between CapabilityRegistry and ProviderRegistry to ensure
    explicitly declared capabilities exist and providers transition cleanly.

    Args:
        capability_registry: Shared capability registry.
        provider_registry: Shared provider registry.
        providers: Optional explicit provider list. When None (default),
            the fabric constructs the standard local provider set.
            Injection is supported for testing only — this is NOT a
            plugin framework.
    """

    def __init__(
        self,
        capability_registry,  # type: ignore[no-untyped-def]
        provider_registry,  # type: ignore[no-untyped-def]
        providers: Sequence[LocalProvider] | None = None,
    ) -> None:
        self.capabilities = capability_registry
        self.providers = provider_registry
        self._instances: dict[str, LocalProvider] = {}
        self._provider_sources: Sequence[LocalProvider] | None = providers

    @property
    def provider_count(self) -> int:
        """Count of constructed local provider instances."""
        return len(self._instances)

    def _build_provider_list(self) -> list[LocalProvider]:
        """Return the list of providers to initialize."""
        if self._provider_sources is not None:
            return list(self._provider_sources)
        return [LocalFilesystemProvider()]

    async def start(self) -> None:
        """Discover, construct, initialize, and register local providers."""
        logger.info("Starting local provider fabric...")

        for prov in self._build_provider_list():
            desc = prov.descriptor
            prov_id = desc.provider_id
            self._instances[prov_id] = prov

            # Register explicitly declared capabilities (no auto-invention)
            await self._ensure_capabilities(prov)

            # Register provider with initial REGISTERED status
            await self.providers.register(desc, overwrite=True)

            # Attempt async initialization
            try:
                await prov.initialize()
                promoted = desc.model_copy(
                    update={"availability": AvailabilityStatus.AVAILABLE},
                )
                await self.providers.register(promoted, overwrite=True)
                logger.info("Local provider '%s' is now AVAILABLE", prov_id)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Provider '%s' init failed, marking UNAVAILABLE: %s",
                    prov_id,
                    exc,
                )
                failed = desc.model_copy(
                    update={"availability": AvailabilityStatus.UNAVAILABLE},
                )
                await self.providers.register(failed, overwrite=True)

    async def stop(self) -> None:
        """Shut down and clean up resources for all local providers."""
        logger.info("Stopping local provider fabric...")
        for prov_id, prov in self._instances.items():
            try:
                await prov.shutdown()
                logger.debug("Shut down provider '%s'", prov_id)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Error shutting down provider '%s': %s", prov_id, exc,
                )
        self._instances.clear()
        logger.info("Local provider fabric stopped")

    async def _ensure_capabilities(self, prov: LocalProvider) -> None:
        """Register only the explicitly declared capabilities for a provider.

        Capabilities not declared via prov.capability_definitions are
        intentionally left unregistered, consistent with ADR-004 which
        permits providers to reference unregistered capability IDs.
        """
        for cap in prov.capability_definitions:
            if not self.capabilities.contains(cap.capability_id):
                await self.capabilities.register(cap)
                logger.debug(
                    "Registered capability '%s' from provider '%s'",
                    cap.capability_id,
                    prov.descriptor.provider_id,
                )
            else:
                logger.debug(
                    "Capability '%s' already registered, skipping",
                    cap.capability_id,
                )
