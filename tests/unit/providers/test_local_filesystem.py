"""Unit tests for LocalFilesystemProvider - S5."""

import pytest
from pydantic import ValidationError

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.providers.base import LocalProvider
from shyam.providers.local.filesystem import (
    FILESYSTEM_CAPABILITIES,
    LocalFilesystemProvider,
)
from shyam.providers.model import Provider


def test_filesystem_provider_instantiation() -> None:
    provider = LocalFilesystemProvider()
    assert isinstance(provider, LocalProvider)

    desc = provider.descriptor
    assert isinstance(desc, Provider)
    assert desc.provider_id == "local.filesystem"
    assert desc.name == "Local Filesystem"
    assert desc.version == "1.0.0"
    assert desc.availability == AvailabilityStatus.REGISTERED
    assert desc.capabilities == ("file.read", "file.write", "file.list")
    assert desc.metadata.get("scope") == "local"


def test_filesystem_capabilities_constant() -> None:
    assert "file.read" in FILESYSTEM_CAPABILITIES
    assert "file.write" in FILESYSTEM_CAPABILITIES
    assert "file.list" in FILESYSTEM_CAPABILITIES


def test_filesystem_capability_definitions_explicit() -> None:
    """Capability definitions are explicit domain objects, not auto-generated."""
    provider = LocalFilesystemProvider()
    defs = provider.capability_definitions
    assert len(defs) == 3
    assert all(isinstance(c, Capability) for c in defs)
    ids = {c.capability_id for c in defs}
    assert ids == {"file.read", "file.write", "file.list"}


def test_descriptor_is_immutable() -> None:
    provider = LocalFilesystemProvider()
    desc = provider.descriptor
    with pytest.raises(ValidationError):
        desc.name = "Mutated Name"  # type: ignore[misc]


def test_no_arbitrary_execution_methods() -> None:
    """Ensure S5 provider is metadata-only and does not implement execution."""
    provider = LocalFilesystemProvider()
    assert not hasattr(provider, "read")
    assert not hasattr(provider, "write")
    assert not hasattr(provider, "list")
    assert not hasattr(provider, "execute")


@pytest.mark.asyncio
async def test_lifecycle_hooks_default_noop() -> None:
    provider = LocalFilesystemProvider()
    await provider.initialize()
    await provider.shutdown()
