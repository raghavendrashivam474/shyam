"""Composite capability registry - S11.

In-memory registry for composite capability definitions.
Separate from the S3 CapabilityRegistry because composites are
composition *recipes*, not primitive ability declarations.

See: docs/adr/ADR-011-composite-registry-separation.md
"""

from __future__ import annotations

import logging

from shyam.composite.errors import CompositeDefinitionError, CompositeNotFoundError
from shyam.composite.models import CompositeCapability

logger = logging.getLogger("shyam.composite.registry")


class CompositeCapabilityRegistry:
    """Manages registration and lookup of composite capability definitions."""

    def __init__(self) -> None:
        self._composites: dict[str, CompositeCapability] = {}

    @property
    def count(self) -> int:
        """Number of registered composites."""
        return len(self._composites)

    def contains(self, capability_id: str) -> bool:
        """Check if a composite is registered."""
        return capability_id in self._composites

    def __contains__(self, capability_id: str) -> bool:
        return self.contains(capability_id)

    def register(
        self,
        composite: CompositeCapability,
        *,
        overwrite: bool = False,
    ) -> None:
        """Register a composite capability definition.

        Args:
            composite: The validated CompositeCapability model.
            overwrite: If True, replaces an existing registration silently.

        Raises:
            CompositeDefinitionError: If the ID already exists and overwrite is False.
        """
        cap_id = composite.capability_id

        if cap_id in self._composites and not overwrite:
            raise CompositeDefinitionError(
                cap_id,
                f"Already registered. Set overwrite=True to replace.",
            )

        is_update = cap_id in self._composites
        self._composites[cap_id] = composite

        logger.info(
            "%s composite capability: %s (v%s)",
            "Updated" if is_update else "Registered",
            cap_id,
            composite.version,
        )

    def get(self, capability_id: str) -> CompositeCapability | None:
        """Retrieve a composite by ID, or None if not registered."""
        return self._composites.get(capability_id)

    def require(self, capability_id: str) -> CompositeCapability:
        """Retrieve a composite by ID, raising if not found."""
        composite = self._composites.get(capability_id)
        if composite is None:
            raise CompositeNotFoundError(capability_id)
        return composite

    def unregister(self, capability_id: str) -> CompositeCapability:
        """Remove a composite by ID.

        Raises:
            CompositeNotFoundError: If not registered.
        """
        composite = self._composites.pop(capability_id, None)
        if composite is None:
            raise CompositeNotFoundError(capability_id)
        logger.info("Unregistered composite capability: %s", capability_id)
        return composite

    def list_all(self) -> list[CompositeCapability]:
        """Return all registered composites."""
        return list(self._composites.values())
