"""Comprehensive Edge Case & Regression Tests for S8 Ecosystem Discovery."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4
import pytest

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.capabilities.registry import CapabilityRegistry
from shyam.discovery.ecosystem_models import (
    DiscoveredCapability,
    DiscoveredNode,
    DiscoveredProvider,
    EcosystemNodeState,
    EcosystemSnapshot,
)
from shyam.discovery.ecosystem_registry import EcosystemRegistry
from shyam.discovery.ecosystem_service import EcosystemDiscoveryService
from shyam.discovery.model import Peer
from shyam.events.bus import EventBus
from shyam.identity.model import NodeIdentity
from shyam.providers.flux.models import FluxPeerInfo
from shyam.providers.model import Provider
from shyam.providers.registry import ProviderRegistry


@pytest.mark.asyncio
async def test_heterogeneous_multi_node_ecosystem():
    """Test full multi-node ecosystem containing Local, UDP peer, and Flux peer."""
    local_id = NodeIdentity(node_id=uuid4(), node_name="node-alpha")
    prov_reg = ProviderRegistry()
    cap_reg = CapabilityRegistry()
    event_bus = EventBus()

    # Local node has local.filesystem
    await cap_reg.register(
        Capability(capability_id="file.read", name="File Read")
    )
    await prov_reg.register(
        Provider(
            provider_id="local.filesystem",
            name="Filesystem",
            capabilities=("file.read",),
        )
    )

    # Mock Flux Provider with 1 remote peer
    mock_flux = MagicMock()
    mock_flux.is_connected = True
    mock_flux.descriptor = Provider(
        provider_id="flux.gateway",
        name="Flux Gateway",
        capabilities=("flux.transfer",),
    )
    mock_flux.capability_definitions = (
        Capability(capability_id="flux.transfer", name="Flux Transfer"),
    )
    mock_flux.discover_peers.return_value = [
        FluxPeerInfo(
            peer_id="12D3KooWPeerX",
            address="/ip4/10.0.0.5/tcp/9000",
            connectivity="reachable",
        )
    ]

    service = EcosystemDiscoveryService(
        local_identity=local_id,
        provider_registry=prov_reg,
        capability_registry=cap_reg,
        flux_provider=mock_flux,
        event_bus=event_bus,
    )

    # Ingest a UDP peer as well
    udp_peer = Peer(
        node_id=uuid4(),
        node_name="node-beta-udp",
        address="10.0.0.6",
        port=54321,
    )
    await service.ingest_udp_peer(udp_peer)

    # Run full discovery
    snapshot = await service.discover()

    # Expect 3 nodes: local (alpha), UDP peer (beta), Flux peer (12D3KooWPeerX)
    assert snapshot.total_nodes == 3
    assert len(snapshot.active_nodes) == 3

    # Check capabilities across ecosystem
    assert "file.read" in snapshot.all_capabilities
    assert "flux.transfer" in snapshot.all_capabilities
    assert "shyam.runtime.inspect" in snapshot.all_capabilities

    # Find nodes by capability
    file_nodes = service.registry.find_nodes_by_capability("file.read")
    assert len(file_nodes) == 1
    assert file_nodes[0].node_id == str(local_id.node_id)

    flux_nodes = service.registry.find_nodes_by_capability("flux.transfer")
    # Local node has flux.gateway and remote node has flux.peer
    assert len(flux_nodes) == 2


@pytest.mark.asyncio
async def test_provider_status_transition_reconciliation():
    """Test that changing provider status updates properly in discovered node view."""
    local_id = NodeIdentity(node_id=uuid4(), node_name="node-test")
    prov_reg = ProviderRegistry()
    cap_reg = CapabilityRegistry()

    service = EcosystemDiscoveryService(
        local_identity=local_id,
        provider_registry=prov_reg,
        capability_registry=cap_reg,
    )

    # 1. Register AVAILABLE provider
    prov = Provider(
        provider_id="local.test",
        name="Test Provider",
        availability=AvailabilityStatus.AVAILABLE,
    )
    await prov_reg.register(prov)
    node1 = await service.discover_local_node()
    assert node1.providers["local.test"].status == AvailabilityStatus.AVAILABLE

    # 2. Update provider to UNAVAILABLE
    failed_prov = prov.model_copy(update={"availability": AvailabilityStatus.UNAVAILABLE})
    await prov_reg.register(failed_prov, overwrite=True)

    node2 = await service.discover_local_node()
    assert node2.providers["local.test"].status == AvailabilityStatus.UNAVAILABLE


@pytest.mark.asyncio
async def test_graceful_handling_of_flux_errors():
    """Test discovery proceeds smoothly even if Flux discover_peers raises an exception."""
    local_id = NodeIdentity(node_id=uuid4(), node_name="node-test")
    prov_reg = ProviderRegistry()
    cap_reg = CapabilityRegistry()

    mock_flux = MagicMock()
    mock_flux.is_connected = True
    mock_flux.descriptor = Provider(
        provider_id="flux.gateway",
        name="Flux Gateway",
        capabilities=("flux.transfer",),
    )
    mock_flux.capability_definitions = (
        Capability(capability_id="flux.transfer", name="Flux Transfer"),
    )
    mock_flux.discover_peers.side_effect = RuntimeError("Flux Gateway connection timeout")

    service = EcosystemDiscoveryService(
        local_identity=local_id,
        provider_registry=prov_reg,
        capability_registry=cap_reg,
        flux_provider=mock_flux,
    )

    snapshot = await service.discover()
    assert snapshot.total_nodes == 1
    assert snapshot.local_node_id == str(local_id.node_id)
