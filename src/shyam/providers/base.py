"""Local Provider implementation contract - S5.

Defines the minimal interface that concrete local providers must satisfy.
A LocalProvider owns a descriptor (the frozen Provider model) and may
declare explicit Capability definitions for the fabric to register.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from shyam.capabilities.model import Capability
from shyam.providers.model import Provider


class LocalProvider(ABC):
    """Abstract base for concrete local provider implementations.

    Subclasses must provide a stable Provider descriptor.
    The descriptor is the canonical metadata representation used
    by the ProviderRegistry and the rest of the Shyam ecosystem.

    Lifecycle:
        1. Constructed by the LocalProviderFabric
        2. descriptor is read and registered
        3. initialize() is called (optional resource setup)
        4. shutdown() is called during runtime stop
    """

    @property
    @abstractmethod
    def descriptor(self) -> Provider:
        """Return the frozen Provider model describing this provider."""
        ...

    @property
    def capability_definitions(self) -> tuple[Capability, ...]:
        """Explicit Capability objects the fabric should ensure are registered.

        Default returns an empty tuple. Override to declare the concrete
        capabilities this provider advertises. No auto-invention occurs;
        only capabilities returned here will be registered by the fabric.
        """
        return ()

    async def initialize(self) -> None:  # noqa: B027
        """Optional async initialization hook for local resources.

        Default is a deliberate no-op. Override only if the provider
        needs to acquire local resources at startup.
        """

    async def shutdown(self) -> None:  # noqa: B027
        """Optional async shutdown hook for local resource cleanup.

        Default is a deliberate no-op. Override only if the provider
        acquired resources during initialize().
        """
