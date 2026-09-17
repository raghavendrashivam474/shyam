"""Unit tests for Discovery models and discovery events."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from shyam.discovery.model import (
    NodeIdentityReadyEvent,
    Peer,
    PeerDiscoveredEvent,
    PeerLostEvent,
    PeerUpdatedEvent,
)


def test_peer_model_instantiation() -> None:
    """Test Peer model creation, fields, and defaults."""
    node_uuid = uuid4()
    peer = Peer(
        node_id=node_uuid,
        node_name="beta-node",
        address="192.168.1.50",
        port=8000,
    )

    assert peer.node_id == node_uuid
    assert peer.node_name == "beta-node"
    assert peer.address == "192.168.1.50"
    assert peer.port == 8000
    assert peer.protocol_version == "0.2.0"
    assert peer.discovered_at is not None
    assert peer.last_seen is not None


def test_peer_immutability() -> None:
    """Peer instances must be immutable."""
    peer = Peer(
        node_id=uuid4(),
        node_name="beta-node",
        address="127.0.0.1",
        port=9000,
    )
    with pytest.raises(ValidationError):
        peer.port = 9001  # type: ignore[misc]


def test_peer_touch_creates_updated_copy() -> None:
    """Calling touch() returns a new instance with a fresh last_seen timestamp."""
    peer = Peer(
        node_id=uuid4(),
        node_name="gamma-node",
        address="127.0.0.1",
        port=9000,
    )
    initial_last_seen = peer.last_seen
    new_time = datetime(2030, 1, 1, 12, 0, 0, tzinfo=UTC)
    touched_peer = peer.touch(seen_at=new_time)

    assert touched_peer.last_seen == new_time
    assert touched_peer.last_seen != initial_last_seen
    assert touched_peer.node_id == peer.node_id


def test_discovery_events_creation() -> None:
    """Verify discovery event models can be instantiated and hold correct payloads."""
    node_uuid = uuid4()
    ready_evt = NodeIdentityReadyEvent(
        node_id=node_uuid,
        node_name="local-node",
        protocol_version="0.2.0",
    )
    assert ready_evt.node_id == node_uuid
    assert ready_evt.event_name == "NodeIdentityReadyEvent"

    peer = Peer(
        node_id=uuid4(),
        node_name="remote-peer",
        address="10.0.0.2",
        port=8080,
    )
    discovered_evt = PeerDiscoveredEvent(peer=peer)
    assert discovered_evt.peer.node_name == "remote-peer"

    updated_evt = PeerUpdatedEvent(peer=peer)
    assert updated_evt.peer.node_id == peer.node_id

    lost_evt = PeerLostEvent(
        node_id=peer.node_id,
        node_name=peer.node_name,
        last_seen=peer.last_seen,
    )
    assert lost_evt.node_id == peer.node_id
