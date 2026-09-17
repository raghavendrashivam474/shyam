"""Unit tests for the Local Peer Discovery Service."""

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from shyam.discovery.model import (
    PeerDiscoveredEvent,
    PeerLostEvent,
    PeerUpdatedEvent,
)
from shyam.discovery.service import DiscoveryService
from shyam.events.bus import EventBus
from shyam.identity.manager import IdentityManager


@pytest.mark.asyncio
async def test_discovery_service_lifecycle(tmp_path: Path) -> None:
    """Verify that start and stop transition states clean up tasks and sockets."""
    bus = EventBus()
    im = IdentityManager(data_dir=tmp_path, custom_node_name="test-active-discovery")

    # Use a high custom port for isolation in unit tests
    service = DiscoveryService(
        identity_manager=im,
        event_bus=bus,
        broadcast_port=58123,
        bind_host="127.0.0.1",
        broadcast_host="127.0.0.1",
    )

    await service.start()
    assert service._running is True
    assert len(service._tasks) == 2
    assert service._transport is not None

    await service.stop()
    assert service._running is False
    assert len(service.peers) == 0
    assert service._transport is None


@pytest.mark.asyncio
async def test_discovery_service_handles_peer_states(tmp_path: Path) -> None:
    """Verify discovery events fire on initial peer creation, updates, and expiration."""
    bus = EventBus()
    im = IdentityManager(data_dir=tmp_path, custom_node_name="host-node")
    im.get_or_create_identity()

    service = DiscoveryService(
        identity_manager=im,
        event_bus=bus,
        broadcast_port=58124,
        broadcast_interval=0.1,
        peer_expiry_interval=0.3,  # Quick expiration for tests
        bind_host="127.0.0.1",
        broadcast_host="127.0.0.1",
    )

    discovered_events = []
    updated_events = []
    lost_events = []

    async def on_disc(e: PeerDiscoveredEvent) -> None:
        discovered_events.append(e.peer)

    async def on_upd(e: PeerUpdatedEvent) -> None:
        updated_events.append(e.peer)

    async def on_lost(e: PeerLostEvent) -> None:
        lost_events.append(e)

    await bus.subscribe(PeerDiscoveredEvent, on_disc)
    await bus.subscribe(PeerUpdatedEvent, on_upd)
    await bus.subscribe(PeerLostEvent, on_lost)

    # 1. Direct datagram processing (simulate incoming broadcast)
    peer_id = uuid4()
    packet = (
        f'{{"node_id": "{peer_id}", "node_name": "remote-xyz", "port": 54321}}'
    ).encode()

    # Handle incoming packet (discovered)
    service.handle_datagram(packet, "127.0.0.1")
    await asyncio.sleep(0.05)  # Let async tasks execute

    assert len(discovered_events) == 1
    assert discovered_events[0].node_id == peer_id
    assert discovered_events[0].node_name == "remote-xyz"

    # 2. Update peer attributes (update event)
    update_packet = (
        f'{{"node_id": "{peer_id}", "node_name": "remote-xyz-updated", "port": 54321}}'
    ).encode()
    service.handle_datagram(update_packet, "127.0.0.1")
    await asyncio.sleep(0.05)

    assert len(updated_events) == 1
    assert updated_events[0].node_name == "remote-xyz-updated"

    # 3. Handle reaping (reaper background task requires service to run)
    await service.start()
    # Mock insert peer with old last_seen to force immediate expiry
    service.handle_datagram(update_packet, "127.0.0.1")
    await asyncio.sleep(0.05)  # Wait for update_peer task to settle

    # Now wait for reap loop to notice peer has decayed (expiry threshold is 0.3s)
    # The reap loop now polls every 0.1s!
    await asyncio.sleep(0.5)

    assert len(lost_events) >= 1
    assert lost_events[0].node_id == peer_id

    await service.stop()
