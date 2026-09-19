"""Local Filesystem Provider - S5.

Represents the local machine's filesystem as a Shyam provider.
This provider advertises file-related capabilities but does NOT
implement execution. Execution is deferred to a later sprint.

Provider ID: local.filesystem
Capabilities: file.read, file.write, file.list
"""

from __future__ import annotations

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.providers.base import LocalProvider
from shyam.providers.model import Provider

# Explicit Capability domain objects for the local filesystem.
# The fabric registers these into the CapabilityRegistry at startup.
# No reflection, no auto-discovery, no heuristic naming.
FILESYSTEM_CAPABILITY_DEFINITIONS: tuple[Capability, ...] = (
    Capability(
        capability_id="file.read",
        name="File Read",
        version="1.0.0",
        description="Read content from the local machine filesystem",
        availability=AvailabilityStatus.AVAILABLE,
    ),
    Capability(
        capability_id="file.write",
        name="File Write",
        version="1.0.0",
        description="Write content to the local machine filesystem",
        availability=AvailabilityStatus.AVAILABLE,
    ),
    Capability(
        capability_id="file.list",
        name="File List",
        version="1.0.0",
        description="List directory contents on the local machine filesystem",
        availability=AvailabilityStatus.AVAILABLE,
    ),
)

FILESYSTEM_CAPABILITIES: tuple[str, ...] = tuple(
    c.capability_id for c in FILESYSTEM_CAPABILITY_DEFINITIONS
)


class LocalFilesystemProvider(LocalProvider):
    """Concrete local provider for the host machine's filesystem.

    This implementation is metadata-only. It provides a stable
    Provider descriptor and manages no external resources.
    """

    def __init__(self) -> None:
        self._descriptor = Provider(
            provider_id="local.filesystem",
            name="Local Filesystem",
            version="1.0.0",
            description="Provides access to the local machine filesystem",
            capabilities=FILESYSTEM_CAPABILITIES,
            metadata={"scope": "local", "type": "filesystem"},
            availability=AvailabilityStatus.REGISTERED,
        )

    @property
    def descriptor(self) -> Provider:
        """Return the frozen Provider descriptor."""
        return self._descriptor

    @property
    def capability_definitions(self) -> tuple[Capability, ...]:
        """Return explicit filesystem capability definitions."""
        return FILESYSTEM_CAPABILITY_DEFINITIONS
