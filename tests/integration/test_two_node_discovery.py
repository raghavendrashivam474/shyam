"""Integration test demonstrating peer discovery and loss between two Shyam nodes."""

import asyncio
from pathlib import Path

import pytest

from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime
from shyam.discovery.model import (
    Peer,
    PeerDiscoveredEvent,
    PeerLostEvent,
)


@pytest.mark.asyncio
async def test_two_nodes_mutual_discovery_and_peer_loss(tmp_path: Path) -> None:
    """Two independent Shyam nodes discover each other over UDP and track departures."""
    shared_port = 58222

    # Node A Configuration
    dir_a = tmp_path / "node_a_data"
    settings_a = ShyamSettings(
        data_directory=dir_a,
        runtime_name="shyam-node-alpha",
        discovery_enabled=True,
        discovery_port=shared_port,
        discovery_interval=0.1,  # Rapid announcement for testing
        discovery_expiry=0.4,  # Fast expiry threshold
    )

    # Node B Configuration
    dir_b = tmp_path / "node_b_data"
    settings_b = ShyamSettings(
        data_directory=dir_b,
        runtime_name="shyam-node-bravo",
        discovery_enabled=True,
        discovery_port=shared_port,
        discovery_interval=0.1,
        discovery_expiry=0.4,
    )

    runtime_a = ShyamRuntime(settings=settings_a)
    runtime_b = ShyamRuntime(settings=settings_b)

    # Event tracking sinks
    a_discovered_peers: list[Peer] = []
    a_lost_peers: list[PeerLostEvent] = []

    b_discovered_peers: list[Peer] = []

    async def on_a_discovered(e: PeerDiscoveredEvent) -> None:
        a_discovered_peers.append(e.peer)

    async def on_a_lost(e: PeerLostEvent) -> None:
        a_lost_peers.append(e)

    async def on_b_discovered(e: PeerDiscoveredEvent) -> None:
        b_discovered_peers.append(e.peer)

    await runtime_a.events.subscribe(PeerDiscoveredEvent, on_a_discovered)
    await runtime_a.events.subscribe(PeerLostEvent, on_a_lost)
    await runtime_b.events.subscribe(PeerDiscoveredEvent, on_b_discovered)

    try:
        # 1. Start Node A
        await runtime_a.start()
        ident_a = runtime_a.identity_manager.identity
        assert ident_a is not None

        # 2. Start Node B
        await runtime_b.start()
        ident_b = runtime_b.identity_manager.identity
        assert ident_b is not None

        # 3. Allow discovery loop to broadcast and receive datagrams
        # Nodes announce every 0.1s
        await asyncio.sleep(0.4)

        # Assert Node A discovered Node B
        assert any(p.node_id == ident_b.node_id for p in a_discovered_peers), (
            f"Node A failed to discover Node B! Seen: {a_discovered_peers}"
        )
        # Assert Node B discovered Node A
        assert any(p.node_id == ident_a.node_id for p in b_discovered_peers), (
            f"Node B failed to discover Node A! Seen: {b_discovered_peers}"
        )

        # 4. Stop Node B (simulate departure / offline crash)
        await runtime_b.stop()

        # 5. Wait for Node A's reaper loop to detect Node B has timed out (> 0.4s)
        await asyncio.sleep(0.6)

        # Assert Node A fired PeerLostEvent for Node B
        assert any(e.node_id == ident_b.node_id for e in a_lost_peers), (
            f"Node A failed to detect loss of Node B! Lost events: {a_lost_peers}"
        )

    finally:
        # Clean shutdown
        if runtime_a.is_running:
            await runtime_a.stop()
        if runtime_b.is_running:
            await runtime_b.stop()
