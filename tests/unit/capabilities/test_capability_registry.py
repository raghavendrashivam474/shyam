"""Unit tests for Shyam CapabilityRegistry."""

import pytest

from shyam.capabilities.exceptions import (
    CapabilityNotFoundError,
    DuplicateCapabilityError,
)
from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.capabilities.registry import CapabilityRegistry


class TestCapabilityRegistry:
    """Tests for CapabilityRegistry registration, retrieval, and querying."""

    @pytest.fixture
    def registry(self) -> CapabilityRegistry:
        return CapabilityRegistry()

    @pytest.fixture
    def sample_capabilities(self) -> list[Capability]:
        return [
            Capability(
                capability_id="file.read",
                name="Read File",
                availability=AvailabilityStatus.AVAILABLE,
            ),
            Capability(
                capability_id="file.write",
                name="Write File",
                availability=AvailabilityStatus.REGISTERED,
            ),
            Capability(
                capability_id="screen.capture",
                name="Screen Capture",
                availability=AvailabilityStatus.AVAILABLE,
            ),
            Capability(
                capability_id="audio.record",
                name="Audio Record",
                availability=AvailabilityStatus.UNAVAILABLE,
            ),
        ]

    async def test_register_and_get(self, registry: CapabilityRegistry) -> None:
        """Registering a capability makes it retrievable by ID."""
        cap = Capability(capability_id="file.read", name="Read File")
        await registry.register(cap)

        assert registry.count == 1
        assert registry.contains("file.read")
        assert "file.read" in registry
        assert registry.get("file.read") == cap

    def test_get_nonexistent_returns_none(self, registry: CapabilityRegistry) -> None:
        """Getting an unregistered capability returns None."""
        assert registry.get("missing.cap") is None
        assert not registry.contains("missing.cap")

    async def test_duplicate_registration_raises(
        self, registry: CapabilityRegistry
    ) -> None:
        """Duplicate registration without overwrite=True raises DuplicateCapabilityError."""
        cap1 = Capability(capability_id="file.read", name="Read V1")
        cap2 = Capability(capability_id="file.read", name="Read V2")

        await registry.register(cap1)
        with pytest.raises(DuplicateCapabilityError):
            await registry.register(cap2)

        # Value should remain unchanged
        assert registry.get("file.read") == cap1

    async def test_overwrite_registration_succeeds(
        self, registry: CapabilityRegistry
    ) -> None:
        """Registration with overwrite=True replaces existing capability."""
        cap1 = Capability(capability_id="file.read", name="Read V1")
        cap2 = Capability(capability_id="file.read", name="Read V2", version="2.0.0")

        await registry.register(cap1)
        await registry.register(cap2, overwrite=True)

        assert registry.count == 1
        assert registry.get("file.read") == cap2

    async def test_unregister(self, registry: CapabilityRegistry) -> None:
        """Unregister removes capability and returns it."""
        cap = Capability(capability_id="file.read", name="Read File")
        await registry.register(cap)

        removed = await registry.unregister("file.read")
        assert removed == cap
        assert registry.count == 0
        assert not registry.contains("file.read")

    async def test_unregister_nonexistent_raises(
        self, registry: CapabilityRegistry
    ) -> None:
        """Unregistering a nonexistent capability raises CapabilityNotFoundError."""
        with pytest.raises(CapabilityNotFoundError):
            await registry.unregister("does.not.exist")

    async def test_list_all(
        self,
        registry: CapabilityRegistry,
        sample_capabilities: list[Capability],
    ) -> None:
        """list_all returns all registered capabilities."""
        for cap in sample_capabilities:
            await registry.register(cap)

        all_caps = registry.list_all()
        assert len(all_caps) == 4
        assert {c.capability_id for c in all_caps} == {
            "file.read",
            "file.write",
            "screen.capture",
            "audio.record",
        }

    async def test_find_by_namespace(
        self,
        registry: CapabilityRegistry,
        sample_capabilities: list[Capability],
    ) -> None:
        """find matches by dot-separated namespace prefix."""
        for cap in sample_capabilities:
            await registry.register(cap)

        file_caps = registry.find(namespace="file")
        assert len(file_caps) == 2
        assert {c.capability_id for c in file_caps} == {"file.read", "file.write"}

        screen_caps = registry.find(namespace="screen")
        assert len(screen_caps) == 1
        assert screen_caps[0].capability_id == "screen.capture"

    async def test_find_by_availability(
        self,
        registry: CapabilityRegistry,
        sample_capabilities: list[Capability],
    ) -> None:
        """find filters by AvailabilityStatus."""
        for cap in sample_capabilities:
            await registry.register(cap)

        avail_caps = registry.find(availability=AvailabilityStatus.AVAILABLE)
        assert len(avail_caps) == 2
        assert {c.capability_id for c in avail_caps} == {
            "file.read",
            "screen.capture",
        }

    async def test_find_by_namespace_and_availability(
        self,
        registry: CapabilityRegistry,
        sample_capabilities: list[Capability],
    ) -> None:
        """find supports composite filtering."""
        for cap in sample_capabilities:
            await registry.register(cap)

        matches = registry.find(
            namespace="file",
            availability=AvailabilityStatus.AVAILABLE,
        )
        assert len(matches) == 1
        assert matches[0].capability_id == "file.read"
