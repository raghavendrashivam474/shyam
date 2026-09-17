"""Unit tests for in-process asynchronous EventBus."""

import pytest

from shyam.events.bus import Event, EventBus, RuntimeStartedEvent, RuntimeStoppedEvent


class CustomSampleEvent(Event):
    data: str


@pytest.mark.asyncio
async def test_publish_and_subscribe():
    """Verify that a subscriber receives published events."""
    bus = EventBus()
    received_events = []

    async def sample_handler(event: CustomSampleEvent) -> None:
        received_events.append(event.data)

    await bus.subscribe(CustomSampleEvent, sample_handler)
    await bus.publish(CustomSampleEvent(data="payload-1"))

    assert len(received_events) == 1
    assert received_events[0] == "payload-1"


@pytest.mark.asyncio
async def test_multiple_subscribers():
    """Verify multiple subscribers receive the same event."""
    bus = EventBus()
    sink_a = []
    sink_b = []

    async def handler_a(event: RuntimeStartedEvent) -> None:
        sink_a.append(event.runtime_id)

    async def handler_b(event: RuntimeStartedEvent) -> None:
        sink_b.append(event.runtime_id)

    await bus.subscribe(RuntimeStartedEvent, handler_a)
    await bus.subscribe(RuntimeStartedEvent, handler_b)

    await bus.publish(RuntimeStartedEvent(runtime_id="node-xyz"))

    assert sink_a == ["node-xyz"]
    assert sink_b == ["node-xyz"]


@pytest.mark.asyncio
async def test_unsubscribe():
    """Verify unsubscribing prevents subsequent event delivery."""
    bus = EventBus()
    received = []

    async def handler(event: CustomSampleEvent) -> None:
        received.append(event.data)

    await bus.subscribe(CustomSampleEvent, handler)
    await bus.publish(CustomSampleEvent(data="first"))

    removed = await bus.unsubscribe(CustomSampleEvent, handler)
    assert removed is True

    await bus.publish(CustomSampleEvent(data="second"))
    assert received == ["first"]


@pytest.mark.asyncio
async def test_handler_exception_isolation():
    """Verify that a failing handler does not prevent other handlers from executing."""
    bus = EventBus()
    successful_runs = []

    async def failing_handler(event: RuntimeStoppedEvent) -> None:
        raise ValueError("Handler crash simulation")

    async def passing_handler(event: RuntimeStoppedEvent) -> None:
        successful_runs.append(event.runtime_id)

    await bus.subscribe(RuntimeStoppedEvent, failing_handler)
    await bus.subscribe(RuntimeStoppedEvent, passing_handler)

    # Should not raise exception
    await bus.publish(RuntimeStoppedEvent(runtime_id="node-safe"))

    assert successful_runs == ["node-safe"]
