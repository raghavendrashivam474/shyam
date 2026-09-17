"""Unit tests for EventEnvelope and Envelope-aware EventBus."""

import pytest

from shyam.events.bus import Event, EventBus
from shyam.events.envelope import EventEnvelope


class EnvelopeSampleEvent(Event):
    content: str


@pytest.mark.asyncio
async def test_envelope_wrapping() -> None:
    """Verify raw events can be wrapped in envelopes correctly."""
    evt = EnvelopeSampleEvent(content="test-data")
    envelope = EventEnvelope.wrap(evt, source_node_id="node-123", metadata={"ttl": 5})

    assert envelope.event_id == evt.event_id
    assert envelope.event_type == "EnvelopeSampleEvent"
    assert envelope.occurred_at == evt.timestamp
    assert envelope.payload == evt
    assert envelope.source_node_id == "node-123"
    assert envelope.metadata == {"ttl": 5}


@pytest.mark.asyncio
async def test_bus_routes_enveloped_payloads_to_raw_subscribers() -> None:
    """Verify that when an envelope is published, subscribers to raw event receive payload."""
    bus = EventBus()
    received_payloads: list[EnvelopeSampleEvent] = []

    async def raw_handler(event: EnvelopeSampleEvent) -> None:
        received_payloads.append(event)

    await bus.subscribe(EnvelopeSampleEvent, raw_handler)

    # Publish an envelope
    evt = EnvelopeSampleEvent(content="hello")
    env = EventEnvelope.wrap(evt)
    await bus.publish(env)

    assert len(received_payloads) == 1
    assert received_payloads[0].content == "hello"


@pytest.mark.asyncio
async def test_bus_routes_raw_events_to_envelope_subscribers() -> None:
    """Verify that when a raw event is published, envelope subscribers get a wrapped envelope."""
    bus = EventBus()
    received_envelopes: list[EventEnvelope] = []

    async def envelope_handler(env: EventEnvelope) -> None:
        received_envelopes.append(env)

    await bus.subscribe(EventEnvelope, envelope_handler)

    # Publish direct raw event
    evt = EnvelopeSampleEvent(content="raw-data")
    await bus.publish(evt)

    assert len(received_envelopes) == 1
    envelope = received_envelopes[0]
    assert isinstance(envelope, EventEnvelope)
    assert envelope.payload == evt
    assert envelope.event_type == "EnvelopeSampleEvent"
