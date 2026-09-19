"""Unit tests for Shyam Provider Registry - S4."""

import pytest

from shyam.capabilities.model import AvailabilityStatus
from shyam.events.bus import EventBus
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
from shyam.providers.registry import ProviderRegistry


class TestProviderRegistry:
    """Tests for local in-memory ProviderRegistry."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        return EventBus()

    @pytest.fixture
    def registry(self, event_bus: EventBus) -> ProviderRegistry:
        return ProviderRegistry(event_bus=event_bus)

    @pytest.fixture
    def sample_provider(self) -> Provider:
        return Provider(
            provider_id="local.filesystem",
            name="Local Filesystem",
            version="1.0.0",
            capabilities=("file.read", "file.write"),
            availability=AvailabilityStatus.REGISTERED,
        )

    async def test_register_and_get(
        self,
        registry: ProviderRegistry,
        sample_provider: Provider,
    ) -> None:
        """Register a provider and retrieve it by ID."""
        assert registry.count == 0
        assert not registry.contains("local.filesystem")

        await registry.register(sample_provider)

        assert registry.count == 1
        assert registry.contains("local.filesystem")
        assert "local.filesystem" in registry
        retrieved = registry.get("local.filesystem")
        assert retrieved == sample_provider

    async def test_get_non_existent(self, registry: ProviderRegistry) -> None:
        """Querying a non-existent provider returns None."""
        assert registry.get("does.not.exist") is None

    async def test_duplicate_registration_raises_error(
        self,
        registry: ProviderRegistry,
        sample_provider: Provider,
    ) -> None:
        """Registering duplicate ID without overwrite raises DuplicateProviderError."""
        await registry.register(sample_provider)
        with pytest.raises(DuplicateProviderError) as exc_info:
            await registry.register(sample_provider)
        assert "already registered" in str(exc_info.value)

    async def test_overwrite_existing_registration(
        self,
        registry: ProviderRegistry,
        sample_provider: Provider,
    ) -> None:
        """Registering with overwrite=True updates the provider."""
        await registry.register(sample_provider)
        updated = Provider(
            provider_id="local.filesystem",
            name="Local Filesystem (Updated)",
            version="1.1.0",
            capabilities=("file.read", "file.write", "file.delete"),
            availability=AvailabilityStatus.AVAILABLE,
        )
        await registry.register(updated, overwrite=True)

        assert registry.count == 1
        retrieved = registry.get("local.filesystem")
        assert retrieved is not None
        assert retrieved.name == "Local Filesystem (Updated)"
        assert retrieved.version == "1.1.0"
        assert retrieved.capabilities == ("file.read", "file.write", "file.delete")

    async def test_unregister_provider(
        self,
        registry: ProviderRegistry,
        sample_provider: Provider,
    ) -> None:
        """Unregister removes and returns the provider."""
        await registry.register(sample_provider)
        assert registry.contains("local.filesystem")

        removed = await registry.unregister("local.filesystem")
        assert removed == sample_provider
        assert registry.count == 0
        assert not registry.contains("local.filesystem")

    async def test_unregister_non_existent_raises_error(
        self,
        registry: ProviderRegistry,
    ) -> None:
        """Unregistering a non-existent provider raises ProviderNotFoundError."""
        with pytest.raises(ProviderNotFoundError):
            await registry.unregister("missing.provider")

    async def test_list_all(self, registry: ProviderRegistry) -> None:
        """list_all returns all registered providers."""
        prov1 = Provider(provider_id="local.fs", name="FS")
        prov2 = Provider(provider_id="local.term", name="Term")

        await registry.register(prov1)
        await registry.register(prov2)

        all_providers = registry.list_all()
        assert len(all_providers) == 2
        assert prov1 in all_providers
        assert prov2 in all_providers

    async def test_find_with_filters(self, registry: ProviderRegistry) -> None:
        """find filters by namespace and availability status."""
        p1 = Provider(
            provider_id="local.fs",
            name="FS",
            availability=AvailabilityStatus.AVAILABLE,
        )
        p2 = Provider(
            provider_id="local.term",
            name="Term",
            availability=AvailabilityStatus.REGISTERED,
        )
        p3 = Provider(
            provider_id="cloud.backup",
            name="Cloud",
            availability=AvailabilityStatus.AVAILABLE,
        )

        await registry.register(p1)
        await registry.register(p2)
        await registry.register(p3)

        # Namespace filter
        local_providers = registry.find(namespace="local")
        assert len(local_providers) == 2

        # Availability filter
        avail_providers = registry.find(availability=AvailabilityStatus.AVAILABLE)
        assert len(avail_providers) == 2

        # Combined filter
        both = registry.find(namespace="local", availability=AvailabilityStatus.AVAILABLE)
        assert len(both) == 1
        assert both[0].provider_id == "local.fs"

    async def test_find_by_capability_multiple_providers(
        self,
        registry: ProviderRegistry,
    ) -> None:
        """find_by_capability must identify all providers claiming that capability."""
        # Provider A provides file.read
        p_a = Provider(
            provider_id="provider.alpha",
            name="Alpha Provider",
            capabilities=("file.read",),
        )
        # Provider B provides file.read and file.write
        p_b = Provider(
            provider_id="provider.beta",
            name="Beta Provider",
            capabilities=("file.read", "file.write"),
        )
        # Provider C provides terminal.exec only
        p_c = Provider(
            provider_id="provider.gamma",
            name="Gamma Provider",
            capabilities=("terminal.exec",),
        )

        await registry.register(p_a)
        await registry.register(p_b)
        await registry.register(p_c)

        # file.read should match Alpha and Beta
        file_read_providers = registry.find_by_capability("file.read")
        assert len(file_read_providers) == 2
        provider_ids = [p.provider_id for p in file_read_providers]
        assert "provider.alpha" in provider_ids
        assert "provider.beta" in provider_ids

        # file.write should match Beta only
        file_write_providers = registry.find_by_capability("file.write")
        assert len(file_write_providers) == 1
        assert file_write_providers[0].provider_id == "provider.beta"

        # non-existent capability should return empty list
        none_providers = registry.find_by_capability("nonexistent.capability")
        assert none_providers == []

    async def test_event_emission_on_lifecycle(
        self,
        registry: ProviderRegistry,
        event_bus: EventBus,
        sample_provider: Provider,
    ) -> None:
        """Registry publishes events to EventBus on register, update, and unregister."""
        events: list[object] = []

        async def capture_event(event: object) -> None:
            events.append(event)

        await event_bus.subscribe(ProviderRegisteredEvent, capture_event)
        await event_bus.subscribe(ProviderUpdatedEvent, capture_event)
        await event_bus.subscribe(ProviderUnregisteredEvent, capture_event)

        # Register
        await registry.register(sample_provider)
        assert len(events) == 1
        assert isinstance(events[0], ProviderRegisteredEvent)
        assert events[0].provider_id == "local.filesystem"

        # Update
        updated = Provider(
            provider_id="local.filesystem",
            name="Local Filesystem Updated",
            availability=AvailabilityStatus.AVAILABLE,
        )
        await registry.register(updated, overwrite=True)
        assert len(events) == 2
        assert isinstance(events[1], ProviderUpdatedEvent)
        assert events[1].previous_availability == "registered"

        # Unregister
        await registry.unregister("local.filesystem")
        assert len(events) == 3
        assert isinstance(events[2], ProviderUnregisteredEvent)
        assert events[2].provider_id == "local.filesystem"
