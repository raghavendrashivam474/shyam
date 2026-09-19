"""Unit tests for LocalProviderFabric - S5."""

import pytest

from shyam.capabilities.model import AvailabilityStatus
from shyam.capabilities.registry import CapabilityRegistry
from shyam.events.bus import EventBus
from shyam.providers.base import LocalProvider
from shyam.providers.events import ProviderRegisteredEvent, ProviderUpdatedEvent
from shyam.providers.fabric import LocalProviderFabric
from shyam.providers.model import Provider
from shyam.providers.registry import ProviderRegistry


@pytest.mark.asyncio
async def test_fabric_startup_registers_providers_and_capabilities() -> None:
    event_bus = EventBus()
    cap_reg = CapabilityRegistry(event_bus=event_bus)
    prov_reg = ProviderRegistry(event_bus=event_bus)
    fabric = LocalProviderFabric(cap_reg, prov_reg)

    assert fabric.provider_count == 0
    assert prov_reg.count == 0

    await fabric.start()

    assert fabric.provider_count == 1
    assert prov_reg.count == 1
    assert prov_reg.contains("local.filesystem")
    assert cap_reg.contains("file.read")
    assert cap_reg.contains("file.write")
    assert cap_reg.contains("file.list")

    fs = prov_reg.get("local.filesystem")
    assert fs is not None
    assert fs.availability == AvailabilityStatus.AVAILABLE


@pytest.mark.asyncio
async def test_fabric_publishes_lifecycle_events() -> None:
    event_bus = EventBus()
    cap_reg = CapabilityRegistry(event_bus=event_bus)
    prov_reg = ProviderRegistry(event_bus=event_bus)
    fabric = LocalProviderFabric(cap_reg, prov_reg)

    registered: list[ProviderRegisteredEvent] = []
    updated: list[ProviderUpdatedEvent] = []

    async def on_reg(e: ProviderRegisteredEvent) -> None:
        registered.append(e)

    async def on_upd(e: ProviderUpdatedEvent) -> None:
        updated.append(e)

    await event_bus.subscribe(ProviderRegisteredEvent, on_reg)
    await event_bus.subscribe(ProviderUpdatedEvent, on_upd)

    await fabric.start()

    assert len(registered) == 1
    assert registered[0].provider_id == "local.filesystem"
    assert len(updated) == 1
    assert updated[0].provider.availability == AvailabilityStatus.AVAILABLE


class _FailingProvider(LocalProvider):
    """Test-only provider whose initialize() always raises."""

    @property
    def descriptor(self) -> Provider:
        return Provider(
            provider_id="local.failing",
            name="Failing Provider",
            version="1.0.0",
            capabilities=("fail.cap",),
            availability=AvailabilityStatus.REGISTERED,
        )

    async def initialize(self) -> None:
        raise RuntimeError("Simulated initialization failure")


@pytest.mark.asyncio
async def test_fabric_marks_failed_provider_unavailable() -> None:
    """Fabric catches init failures and marks provider UNAVAILABLE."""
    cap_reg = CapabilityRegistry()
    prov_reg = ProviderRegistry()
    fabric = LocalProviderFabric(
        cap_reg,
        prov_reg,
        providers=[_FailingProvider()],
    )

    await fabric.start()

    assert prov_reg.count == 1
    failing = prov_reg.get("local.failing")
    assert failing is not None
    assert failing.availability == AvailabilityStatus.UNAVAILABLE


class _ShutdownExplodingProvider(LocalProvider):
    """Test-only provider whose shutdown() always raises."""

    @property
    def descriptor(self) -> Provider:
        return Provider(
            provider_id="local.boom",
            name="Boom Provider",
            version="1.0.0",
        )

    async def shutdown(self) -> None:
        raise RuntimeError("Simulated shutdown failure")


@pytest.mark.asyncio
async def test_fabric_stop_survives_shutdown_errors() -> None:
    """Fabric stop() continues even if a provider's shutdown raises."""
    cap_reg = CapabilityRegistry()
    prov_reg = ProviderRegistry()
    fabric = LocalProviderFabric(
        cap_reg,
        prov_reg,
        providers=[_ShutdownExplodingProvider()],
    )

    await fabric.start()
    assert fabric.provider_count == 1

    # Must not raise despite shutdown failure
    await fabric.stop()
    assert fabric.provider_count == 0


@pytest.mark.asyncio
async def test_fabric_stop_cleans_up() -> None:
    cap_reg = CapabilityRegistry()
    prov_reg = ProviderRegistry()
    fabric = LocalProviderFabric(cap_reg, prov_reg)

    await fabric.start()
    assert fabric.provider_count == 1

    await fabric.stop()
    assert fabric.provider_count == 0
