"""Unit tests for ReadinessTracker and Ecosystem Readiness Lifecycle (S17.5)."""

import asyncio
from unittest.mock import MagicMock

import pytest

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.capabilities.registry import CapabilityRegistry
from shyam.core.readiness import (
    ComponentReadinessChangedEvent,
    ComponentState,
    EcosystemReadiness,
    EcosystemReadinessChangedEvent,
    ReadinessTracker,
)
from shyam.events.bus import EventBus
from shyam.providers.model import Provider
from shyam.providers.registry import ProviderRegistry


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def provider_registry(event_bus: EventBus) -> ProviderRegistry:
    return ProviderRegistry(event_bus=event_bus)


@pytest.fixture
def capability_registry(event_bus: EventBus) -> CapabilityRegistry:
    return CapabilityRegistry(event_bus=event_bus)


def create_mock_zarya_provider(
    is_connected: bool = True,
    refresh_status_val: AvailabilityStatus = AvailabilityStatus.AVAILABLE,
) -> MagicMock:
    provider = MagicMock()
    provider._is_connected = is_connected
    provider.connect.return_value = is_connected
    provider.refresh_status.return_value = refresh_status_val
    provider.descriptor = Provider(
        provider_id="zarya.local",
        name="Zarya Provider",
        version="1.0.0",
        capabilities=("agent.execute", "agent.continue"),
        metadata={},
    )
    provider.capability_definitions = [
        Capability(
            capability_id="agent.execute",
            name="Zarya Execute",
            version="1.0.0",
            description="Execute agent task",
            availability=AvailabilityStatus.AVAILABLE,
        )
    ]
    return provider


def create_mock_flux_provider(
    is_connected: bool = True,
    refresh_status_val: AvailabilityStatus = AvailabilityStatus.AVAILABLE,
    peer_id: str = "flux-peer-123",
) -> MagicMock:
    provider = MagicMock()
    provider._is_connected = is_connected
    provider.connect.return_value = is_connected
    provider.refresh_status.return_value = refresh_status_val
    provider.peer_id = peer_id
    provider.descriptor = Provider(
        provider_id="flux.local",
        name="Flux Provider",
        version="1.0.0",
        capabilities=("flux.transfer",),
        metadata={},
    )
    provider.capability_definitions = [
        Capability(
            capability_id="flux.transfer",
            name="Flux Transfer",
            version="1.0.0",
            description="Transfer artifacts",
            availability=AvailabilityStatus.AVAILABLE,
        )
    ]
    return provider


@pytest.mark.asyncio
async def test_readiness_tracker_initial_state(
    event_bus: EventBus,
    provider_registry: ProviderRegistry,
    capability_registry: CapabilityRegistry,
) -> None:
    """ReadinessTracker starts in STARTING state until components are evaluated."""
    zarya = create_mock_zarya_provider()
    flux = create_mock_flux_provider()

    tracker = ReadinessTracker(
        event_bus=event_bus,
        zarya_provider=zarya,
        flux_provider=flux,
        provider_registry=provider_registry,
        capability_registry=capability_registry,
        poll_interval=10.0,
    )

    assert tracker.readiness == EcosystemReadiness.STARTING
    assert not tracker.is_ready

    snapshot = tracker.get_snapshot()
    assert snapshot.readiness == EcosystemReadiness.STARTING
    assert snapshot.components["node"].state == ComponentState.STARTING
    assert snapshot.components["zarya"].state == ComponentState.STARTING
    assert snapshot.components["flux"].state == ComponentState.STARTING


@pytest.mark.asyncio
async def test_readiness_all_ready(
    event_bus: EventBus,
    provider_registry: ProviderRegistry,
    capability_registry: CapabilityRegistry,
) -> None:
    """When node, Zarya, and Flux are ready, ecosystem readiness becomes READY."""
    zarya = create_mock_zarya_provider(is_connected=True)
    flux = create_mock_flux_provider(is_connected=True)

    tracker = ReadinessTracker(
        event_bus=event_bus,
        zarya_provider=zarya,
        flux_provider=flux,
        provider_registry=provider_registry,
        capability_registry=capability_registry,
        poll_interval=10.0,
    )

    tracker.set_node_ready()
    snapshot = await tracker.poll_now()

    assert snapshot.readiness == EcosystemReadiness.READY
    assert snapshot.is_ready
    assert snapshot.components["node"].state == ComponentState.READY
    assert snapshot.components["zarya"].state == ComponentState.READY
    assert snapshot.components["flux"].state == ComponentState.READY


@pytest.mark.asyncio
async def test_readiness_degraded_when_zarya_unavailable(
    event_bus: EventBus,
    provider_registry: ProviderRegistry,
    capability_registry: CapabilityRegistry,
) -> None:
    """When Zarya is unavailable but Flux is ready, ecosystem is DEGRADED."""
    zarya = create_mock_zarya_provider(is_connected=False)
    flux = create_mock_flux_provider(is_connected=True)

    tracker = ReadinessTracker(
        event_bus=event_bus,
        zarya_provider=zarya,
        flux_provider=flux,
        provider_registry=provider_registry,
        capability_registry=capability_registry,
        poll_interval=10.0,
    )

    tracker.set_node_ready()
    snapshot = await tracker.poll_now()

    assert snapshot.readiness == EcosystemReadiness.DEGRADED
    assert not snapshot.is_ready
    assert snapshot.components["zarya"].state == ComponentState.UNAVAILABLE
    assert snapshot.components["flux"].state == ComponentState.READY


@pytest.mark.asyncio
async def test_readiness_degraded_when_flux_unavailable(
    event_bus: EventBus,
    provider_registry: ProviderRegistry,
    capability_registry: CapabilityRegistry,
) -> None:
    """When Flux is unavailable but Zarya is ready, ecosystem is DEGRADED."""
    zarya = create_mock_zarya_provider(is_connected=True)
    flux = create_mock_flux_provider(is_connected=False)

    tracker = ReadinessTracker(
        event_bus=event_bus,
        zarya_provider=zarya,
        flux_provider=flux,
        provider_registry=provider_registry,
        capability_registry=capability_registry,
        poll_interval=10.0,
    )

    tracker.set_node_ready()
    snapshot = await tracker.poll_now()

    assert snapshot.readiness == EcosystemReadiness.DEGRADED
    assert not snapshot.is_ready
    assert snapshot.components["zarya"].state == ComponentState.READY
    assert snapshot.components["flux"].state == ComponentState.UNAVAILABLE


@pytest.mark.asyncio
async def test_delayed_component_startup_detection(
    event_bus: EventBus,
    provider_registry: ProviderRegistry,
    capability_registry: CapabilityRegistry,
) -> None:
    """ReadinessTracker detects when delayed components come online later."""
    zarya = create_mock_zarya_provider(is_connected=False)
    flux = create_mock_flux_provider(is_connected=True)

    tracker = ReadinessTracker(
        event_bus=event_bus,
        zarya_provider=zarya,
        flux_provider=flux,
        provider_registry=provider_registry,
        capability_registry=capability_registry,
        poll_interval=10.0,
    )

    tracker.set_node_ready()

    # Initial check: Zarya is offline -> DEGRADED
    snap1 = await tracker.poll_now()
    assert snap1.readiness == EcosystemReadiness.DEGRADED
    assert snap1.components["zarya"].state == ComponentState.UNAVAILABLE

    # Zarya finishes starting up
    zarya._is_connected = True
    zarya.connect.return_value = True

    # Next poll discovers Zarya is now ready -> READY
    snap2 = await tracker.poll_now()
    assert snap2.readiness == EcosystemReadiness.READY
    assert snap2.components["zarya"].state == ComponentState.READY

    # Capabilities should have been registered dynamically
    assert capability_registry.contains("agent.execute")


@pytest.mark.asyncio
async def test_component_crash_and_recovery(
    event_bus: EventBus,
    provider_registry: ProviderRegistry,
    capability_registry: CapabilityRegistry,
) -> None:
    """ReadinessTracker detects when a running component crashes and later recovers."""
    flux = create_mock_flux_provider(is_connected=True)
    zarya = create_mock_zarya_provider(is_connected=True)

    tracker = ReadinessTracker(
        event_bus=event_bus,
        zarya_provider=zarya,
        flux_provider=flux,
        provider_registry=provider_registry,
        capability_registry=capability_registry,
        poll_interval=10.0,
    )

    tracker.set_node_ready()
    snap1 = await tracker.poll_now()
    assert snap1.readiness == EcosystemReadiness.READY

    # Flux crashes: refresh_status returns UNAVAILABLE
    flux.refresh_status.return_value = AvailabilityStatus.UNAVAILABLE
    snap2 = await tracker.poll_now()
    assert snap2.readiness == EcosystemReadiness.DEGRADED
    assert snap2.components["flux"].state == ComponentState.UNAVAILABLE

    # Flux recovers
    flux.refresh_status.return_value = AvailabilityStatus.AVAILABLE
    snap3 = await tracker.poll_now()
    assert snap3.readiness == EcosystemReadiness.READY
    assert snap3.components["flux"].state == ComponentState.READY


@pytest.mark.asyncio
async def test_readiness_events_published(
    event_bus: EventBus,
    provider_registry: ProviderRegistry,
    capability_registry: CapabilityRegistry,
) -> None:
    """ComponentReadinessChangedEvent and EcosystemReadinessChangedEvent are published on state changes."""
    zarya = create_mock_zarya_provider(is_connected=False)
    flux = create_mock_flux_provider(is_connected=False)

    component_events: list[ComponentReadinessChangedEvent] = []
    ecosystem_events: list[EcosystemReadinessChangedEvent] = []

    async def _on_comp_event(ev: ComponentReadinessChangedEvent) -> None:
        component_events.append(ev)

    async def _on_eco_event(ev: EcosystemReadinessChangedEvent) -> None:
        ecosystem_events.append(ev)

    await event_bus.subscribe(ComponentReadinessChangedEvent, _on_comp_event)
    await event_bus.subscribe(EcosystemReadinessChangedEvent, _on_eco_event)

    tracker = ReadinessTracker(
        event_bus=event_bus,
        zarya_provider=zarya,
        flux_provider=flux,
        provider_registry=provider_registry,
        capability_registry=capability_registry,
        poll_interval=10.0,
    )

    tracker.set_node_ready()
    await tracker.poll_now()

    # Yield control to let async event handlers run
    await asyncio.sleep(0.01)

    assert any(e.component == "node" and e.new_state == ComponentState.READY for e in component_events)
    assert any(e.new_readiness == EcosystemReadiness.DEGRADED for e in ecosystem_events)


@pytest.mark.asyncio
async def test_tracker_background_start_and_stop(
    event_bus: EventBus,
    provider_registry: ProviderRegistry,
    capability_registry: CapabilityRegistry,
) -> None:
    """ReadinessTracker starts background polling task and cancels it cleanly upon stop()."""
    zarya = create_mock_zarya_provider(is_connected=True)
    flux = create_mock_flux_provider(is_connected=True)

    tracker = ReadinessTracker(
        event_bus=event_bus,
        zarya_provider=zarya,
        flux_provider=flux,
        provider_registry=provider_registry,
        capability_registry=capability_registry,
        poll_interval=0.05,
    )

    tracker.set_node_ready()
    await tracker.start()
    assert tracker._running
    assert tracker._poll_task is not None

    # Wait for at least one poll round in background
    await asyncio.sleep(0.12)
    assert tracker.is_ready

    await tracker.stop()
    assert not tracker._running
    assert tracker._poll_task is None
