"""Unit tests for S8 Ecosystem Discovery Models."""

from datetime import UTC, datetime
from uuid import uuid4

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.discovery.ecosystem_models import (
    DiscoveredCapability,
    DiscoveredNode,
    DiscoveredProvider,
    EcosystemNodeState,
    EcosystemSnapshot,
)
from shyam.providers.model import Provider


def test_discovered_capability_from_capability():
    cap = Capability(
        capability_id="file.read",
        name="File Reader",
        version="1.2.0",
        description="Reads local files",
        availability=AvailabilityStatus.AVAILABLE,
    )
    disc_cap = DiscoveredCapability.from_capability(cap)
    assert disc_cap.capability_id == "file.read"
    assert disc_cap.name == "File Reader"
    assert disc_cap.version == "1.2.0"
    assert disc_cap.availability == AvailabilityStatus.AVAILABLE


def test_discovered_provider_from_provider():
    cap = Capability(
        capability_id="file.read",
        name="File Reader",
    )
    prov = Provider(
        provider_id="local.filesystem",
        name="Local Filesystem",
        version="1.0.0",
        capabilities=("file.read",),
        availability=AvailabilityStatus.AVAILABLE,
    )
    disc_prov = DiscoveredProvider.from_provider(
        provider=prov,
        capability_models=(cap,),
    )
    assert disc_prov.provider_id == "local.filesystem"
    assert disc_prov.name == "Local Filesystem"
    assert disc_prov.status == AvailabilityStatus.AVAILABLE
    assert disc_prov.capability_ids == ("file.read",)
    assert len(disc_prov.capabilities) == 1
    assert disc_prov.capabilities[0].name == "File Reader"


def test_discovered_node_immutability_and_methods():
    node = DiscoveredNode(
        node_id="node-123",
        node_name="Node One",
        state=EcosystemNodeState.KNOWN,
        is_local=True,
    )
    assert node.node_id == "node-123"
    assert node.state == EcosystemNodeState.KNOWN
    assert node.is_local is True

    # Touch
    now = datetime.now(UTC)
    touched = node.with_touch(seen_at=now)
    assert touched.last_seen == now
    assert touched.node_id == node.node_id

    # State update
    available = node.with_state(EcosystemNodeState.AVAILABLE)
    assert available.state == EcosystemNodeState.AVAILABLE

    # Provider add
    prov = DiscoveredProvider(
        provider_id="test.provider",
        name="Test",
        capabilities=(DiscoveredCapability(capability_id="test.cap"),),
    )
    with_prov = node.with_provider(prov)
    assert "test.provider" in with_prov.providers
    assert "test.cap" in with_prov.capability_ids

    # Provider remove
    without_prov = with_prov.without_provider("test.provider")
    assert "test.provider" not in without_prov.providers
    assert len(without_prov.capability_ids) == 0


def test_ecosystem_snapshot():
    node1 = DiscoveredNode(
        node_id="node-1",
        node_name="Node 1",
        state=EcosystemNodeState.AVAILABLE,
        is_local=True,
        providers={
            "local.fs": DiscoveredProvider(
                provider_id="local.fs",
                name="FS",
                capabilities=(DiscoveredCapability(capability_id="file.read"),),
            )
        },
    )
    node2 = DiscoveredNode(
        node_id="node-2",
        node_name="Node 2",
        state=EcosystemNodeState.STALE,
        is_local=False,
    )
    snapshot = EcosystemSnapshot(
        local_node_id="node-1",
        nodes={"node-1": node1, "node-2": node2},
    )

    assert snapshot.total_nodes == 2
    assert len(snapshot.active_nodes) == 1
    assert snapshot.active_nodes[0].node_id == "node-1"
    assert snapshot.total_providers == 1
    assert snapshot.all_capabilities == {"file.read"}
