"""Unit tests for Capability domain events and EventEnvelope integration."""

from shyam.capabilities.events import (
    CapabilityRegisteredEvent,
    CapabilityUnregisteredEvent,
    CapabilityUpdatedEvent,
)
from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.capabilities.registry import CapabilityRegistry
from shyam.events.bus import EventBus
from shyam.events.envelope import EventEnvelope


class TestCapabilityEvents:
    """Tests for capability event generation and delivery."""

    async def test_registration_emits_registered_event(self) -> None:
        """Registering a capability publishes a CapabilityRegisteredEvent."""
        bus = EventBus()
        events: list[CapabilityRegisteredEvent] = []

        async def handler(event: CapabilityRegisteredEvent) -> None:
            events.append(event)

        await bus.subscribe(CapabilityRegisteredEvent, handler)

        registry = CapabilityRegistry(event_bus=bus)
        cap = Capability(capability_id="file.read", name="Read")
        await registry.register(cap)

        assert len(events) == 1
        assert events[0].capability_id == "file.read"
        assert events[0].capability == cap

    async def test_update_emits_updated_event(self) -> None:
        """Overwriting a capability publishes a CapabilityUpdatedEvent with previous status."""
        bus = EventBus()
        events: list[CapabilityUpdatedEvent] = []

        async def handler(event: CapabilityUpdatedEvent) -> None:
            events.append(event)

        await bus.subscribe(CapabilityUpdatedEvent, handler)

        registry = CapabilityRegistry(event_bus=bus)
        cap1 = Capability(
            capability_id="file.read",
            name="Read V1",
            availability=AvailabilityStatus.REGISTERED,
        )
        cap2 = Capability(
            capability_id="file.read",
            name="Read V2",
            availability=AvailabilityStatus.AVAILABLE,
        )

        await registry.register(cap1)
        await registry.register(cap2, overwrite=True)

        assert len(events) == 1
        assert events[0].capability_id == "file.read"
        assert events[0].capability == cap2
        assert events[0].previous_availability == AvailabilityStatus.REGISTERED.value

    async def test_unregister_emits_unregistered_event(self) -> None:
        """Unregistering publishes a CapabilityUnregisteredEvent."""
        bus = EventBus()
        events: list[CapabilityUnregisteredEvent] = []

        async def handler(event: CapabilityUnregisteredEvent) -> None:
            events.append(event)

        await bus.subscribe(CapabilityUnregisteredEvent, handler)

        registry = CapabilityRegistry(event_bus=bus)
        cap = Capability(capability_id="file.read", name="Read")
        await registry.register(cap)
        await registry.unregister("file.read")

        assert len(events) == 1
        assert events[0].capability_id == "file.read"

    async def test_event_envelope_wrapping(self) -> None:
        """Capability events can be packaged into transport-neutral EventEnvelopes."""
        cap = Capability(capability_id="compute.wasm", name="WASM Engine")
        domain_event = CapabilityRegisteredEvent(
            capability_id="compute.wasm",
            capability=cap,
        )

        envelope = EventEnvelope.wrap(
            event=domain_event,
            source_node_id="node-12345",
        )

        assert envelope.source_node_id == "node-12345"
        assert envelope.event_type == "CapabilityRegisteredEvent"
        assert envelope.payload.capability_id == "compute.wasm"
        assert envelope.payload.capability.name == "WASM Engine"
