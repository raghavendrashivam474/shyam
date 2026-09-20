"""Tests for S9.2 Candidate Discovery."""

from __future__ import annotations

from datetime import UTC, datetime

from shyam.capabilities.model import AvailabilityStatus
from shyam.discovery.ecosystem_models import (
    DiscoveredCapability,
    DiscoveredNode,
    DiscoveredProvider,
    EcosystemNodeState,
    EcosystemSnapshot,
)
from shyam.navigation.candidates import CandidateDiscoverer


def test_discover_candidates_empty_snapshot() -> None:
    snapshot = EcosystemSnapshot(
        local_node_id="local-node",
        nodes={},
    )
    candidates = CandidateDiscoverer.discover_candidates(snapshot, "file.read")
    assert len(candidates) == 0


def test_discover_candidates_no_matching_capability() -> None:
    now = datetime.now(UTC)
    cap = DiscoveredCapability(
        capability_id="file.write",
        name="Write Files",
        availability=AvailabilityStatus.AVAILABLE,
    )
    provider = DiscoveredProvider(
        provider_id="local.fs",
        name="Local FS",
        capabilities=(cap,),
        status=AvailabilityStatus.AVAILABLE,
        last_seen=now,
    )
    node = DiscoveredNode(
        node_id="local-node",
        node_name="Local Node",
        is_local=True,
        state=EcosystemNodeState.AVAILABLE,
        providers={"local.fs": provider},
        first_seen=now,
        last_seen=now,
    )
    snapshot = EcosystemSnapshot(
        local_node_id="local-node",
        nodes={"local-node": node},
    )

    # Looking for file.read, but only file.write is there
    candidates = CandidateDiscoverer.discover_candidates(snapshot, "file.read")
    assert len(candidates) == 0


def test_discover_candidates_successful_match() -> None:
    now = datetime.now(UTC)
    cap = DiscoveredCapability(
        capability_id="file.read",
        name="Read Files",
        availability=AvailabilityStatus.AVAILABLE,
    )
    provider = DiscoveredProvider(
        provider_id="local.fs",
        name="Local FS",
        capabilities=(cap,),
        status=AvailabilityStatus.AVAILABLE,
        last_seen=now,
    )
    node = DiscoveredNode(
        node_id="local-node",
        node_name="Local Node",
        is_local=True,
        state=EcosystemNodeState.AVAILABLE,
        providers={"local.fs": provider},
        first_seen=now,
        last_seen=now,
    )
    snapshot = EcosystemSnapshot(
        local_node_id="local-node",
        nodes={"local-node": node},
    )

    candidates = CandidateDiscoverer.discover_candidates(snapshot, "file.read")
    assert len(candidates) == 1
    c = candidates[0]
    assert c.node_id == "local-node"
    assert c.provider_id == "local.fs"
    assert c.capability_id == "file.read"
    assert c.is_local is True
    assert c.node_state == EcosystemNodeState.AVAILABLE
    assert c.provider_status == AvailabilityStatus.AVAILABLE
    assert c.capability_availability == AvailabilityStatus.AVAILABLE
    
    # Corrected operator precedence/assertion
    expected_node_meta = {"environment": "local"} if "environment" in node.metadata else {}
    assert c.metadata["node"] == expected_node_meta


def test_discover_candidates_multiple_nodes_and_providers() -> None:
    now = datetime.now(UTC)
    cap = DiscoveredCapability(
        capability_id="file.read",
        name="Read Files",
        availability=AvailabilityStatus.AVAILABLE,
    )

    # Local node with local.fs
    local_prov = DiscoveredProvider(
        provider_id="local.fs",
        name="Local FS",
        capabilities=(cap,),
        status=AvailabilityStatus.AVAILABLE,
        last_seen=now,
    )
    local_node = DiscoveredNode(
        node_id="local-node",
        node_name="Local Node",
        is_local=True,
        state=EcosystemNodeState.AVAILABLE,
        providers={"local.fs": local_prov},
        first_seen=now,
        last_seen=now,
    )

    # Remote node with zarya.agent
    zarya_prov = DiscoveredProvider(
        provider_id="zarya.agent",
        name="Zarya",
        capabilities=(cap,),
        status=AvailabilityStatus.AVAILABLE,
        last_seen=now,
    )
    remote_node = DiscoveredNode(
        node_id="remote-node",
        node_name="Remote Node",
        is_local=False,
        state=EcosystemNodeState.AVAILABLE,
        providers={"zarya.agent": zarya_prov},
        first_seen=now,
        last_seen=now,
    )

    snapshot = EcosystemSnapshot(
        local_node_id="local-node",
        nodes={
            "local-node": local_node,
            "remote-node": remote_node,
        },
    )

    candidates = CandidateDiscoverer.discover_candidates(snapshot, "file.read")
    assert len(candidates) == 2

    local_candidates = [c for c in candidates if c.is_local]
    remote_candidates = [c for c in candidates if not c.is_local]

    assert len(local_candidates) == 1
    assert local_candidates[0].node_id == "local-node"
    assert local_candidates[0].provider_id == "local.fs"

    assert len(remote_candidates) == 1
    assert remote_candidates[0].node_id == "remote-node"
    assert remote_candidates[0].provider_id == "zarya.agent"
