"""Unit tests for S8 Ecosystem Discovery Registry."""

import asyncio
from datetime import UTC, datetime, timedelta
import pytest

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.discovery.ecosystem_models import (
    DiscoveredCapability,
    DiscoveredNode,
    DiscoveredProvider,
    EcosystemNodeDiscoveredEvent,
    EcosystemNodeLostEvent,
    EcosystemNodeStaleEvent,
    EcosystemNodeState,
    EcosystemNodeUpdatedEvent,
)
from shyam.discovery.ecosystem_registry import EcosystemRegistry
from shyam.events.bus import EventBus


@pytest.mark.asyncio
async def test_register_and_get_node():
    bus = EventBus()
    events = []

    async def on_discovered(e):
        events.append(e)

    await bus.subscribe(EcosystemNodeDiscoveredEvent, on_discovered)

    reg = EcosystemRegistry(event_bus=bus)
    node = DiscoveredNode(
        node_id="n1",
        node_name="Node 1",
        state=EcosystemNodeState.AVAILABLE,
        is_local=True,
    )
    await reg.register_node(node)

    assert reg.count == 1
    assert reg.contains("n1")
    assert "n1" in reg
    assert reg.get_node("n1") == node
    assert reg.get_local_node() == node
    assert len(events) == 1
    assert events[0].node.node_id == "n1"


@pytest.mark.asyncio
async def test_update_node_and_touch():
    bus = EventBus()
    events = []

    async def on_updated(e):
        events.append(e)

    await bus.subscribe(EcosystemNodeUpdatedEvent, on_updated)

    reg = EcosystemRegistry(event_bus=bus)
    node = DiscoveredNode(
        node_id="n2",
        node_name="Node 2",
        state=EcosystemNodeState.KNOWN,
    )
    await reg.register_node(node)

    # Update state
    updated = await reg.update_node_state("n2", EcosystemNodeState.AVAILABLE)
    assert updated is not None
    assert updated.state == EcosystemNodeState.AVAILABLE
    assert len(events) == 1
    assert events[0].previous_state == EcosystemNodeState.KNOWN

    # Touch
    future_time = datetime.now(UTC) + timedelta(minutes=5)
    touched = await reg.touch_node("n2", seen_at=future_time)
    assert touched is not None
    assert touched.last_seen == future_time


@pytest.mark.asyncio
async def test_add_and_remove_provider():
    reg = EcosystemRegistry()
    node = DiscoveredNode(node_id="n1", node_name="Node 1")
    await reg.register_node(node)

    prov = DiscoveredProvider(
        provider_id="local.fs",
        name="FS",
        capabilities=(DiscoveredCapability(capability_id="file.read"),),
    )
    await reg.add_provider("n1", prov)

    node_after = reg.get_node("n1")
    assert node_after is not None
    assert "local.fs" in node_after.providers
    assert "file.read" in node_after.capability_ids

    # Query by capability / provider
    assert len(reg.find_nodes_by_capability("file.read")) == 1
    assert len(reg.find_nodes_by_provider("local.fs")) == 1
    assert len(reg.find_nodes_by_capability("nonexistent")) == 0

    # Remove provider
    await reg.remove_provider("n1", "local.fs")
    assert "local.fs" not in reg.get_node("n1").providers


@pytest.mark.asyncio
async def test_reconcile_stale():
    bus = EventBus()
    stale_events = []

    async def on_stale(e):
        stale_events.append(e)

    await bus.subscribe(EcosystemNodeStaleEvent, on_stale)

    reg = EcosystemRegistry(event_bus=bus)
    past = datetime.now(UTC) - timedelta(seconds=20)

    # Remote node last seen in past
    remote_node = DiscoveredNode(
        node_id="remote-1",
        node_name="Remote Node",
        state=EcosystemNodeState.AVAILABLE,
        is_local=False,
        last_seen=past,
    )
    # Local node last seen in past (should NOT be marked stale)
    local_node = DiscoveredNode(
        node_id="local-1",
        node_name="Local Node",
        state=EcosystemNodeState.AVAILABLE,
        is_local=True,
        last_seen=past,
    )

    await reg.register_node(remote_node)
    await reg.register_node(local_node)

    stale_ids = await reg.reconcile_stale(stale_threshold_secs=10.0)
    assert stale_ids == ["remote-1"]
    assert reg.get_node("remote-1").state == EcosystemNodeState.STALE
    assert reg.get_node("local-1").state == EcosystemNodeState.AVAILABLE
    assert len(stale_events) == 1
    assert stale_events[0].node_id == "remote-1"


@pytest.mark.asyncio
async def test_remove_node():
    bus = EventBus()
    lost_events = []

    async def on_lost(e):
        lost_events.append(e)

    await bus.subscribe(EcosystemNodeLostEvent, on_lost)

    reg = EcosystemRegistry(event_bus=bus)
    node = DiscoveredNode(node_id="n1", node_name="N1")
    await reg.register_node(node)

    removed = await reg.remove_node("n1")
    assert removed is not None
    assert reg.count == 0
    assert len(lost_events) == 1
    assert lost_events[0].node_id == "n1"


@pytest.mark.asyncio
async def test_create_snapshot():
    reg = EcosystemRegistry()
    node = DiscoveredNode(
        node_id="local-1",
        node_name="Local",
        is_local=True,
        state=EcosystemNodeState.AVAILABLE,
    )
    await reg.register_node(node)

    snapshot = reg.create_snapshot()
    assert snapshot.local_node_id == "local-1"
    assert snapshot.total_nodes == 1
    assert len(snapshot.active_nodes) == 1
