"""Unit tests for S8 Ecosystem Discovery Service & Normalization."""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4
import pytest

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.capabilities.registry import CapabilityRegistry
from shyam.discovery.ecosystem_models import EcosystemNodeState
from shyam.discovery.ecosystem_registry import EcosystemRegistry
from shyam.discovery.ecosystem_service import EcosystemDiscoveryService
from shyam.discovery.model import Peer
from shyam.identity.model import NodeIdentity
from shyam.providers.flux.models import FluxPeerInfo
from shyam.providers.model import Provider
from shyam.providers.registry import ProviderRegistry


@pytest.fixture
def sample_identity():
    return NodeIdentity(
        node_id=uuid4(),
        node_name="test-shyam-node",
    )


@pytest.fixture
def capability_registry():
    return CapabilityRegistry()


@pytest.fixture
def provider_registry():
    return ProviderRegistry()


@pytest.fixture
def ecosystem_service(sample_identity, provider_registry, capability_registry):
    return EcosystemDiscoveryService(
        local_identity=sample_identity,
        provider_registry=provider_registry,
        capability_registry=capability_registry,
    )


@pytest.mark.asyncio
async def test_discover_local_node_with_providers(
    ecosystem_service,
    provider_registry,
    capability_registry,
    sample_identity,
):
    # Setup a local capability and provider
    cap = Capability(
        capability_id="file.read",
        name="Read Files",
        availability=AvailabilityStatus.AVAILABLE,
    )
    await capability_registry.register(cap)

    prov = Provider(
        provider_id="local.filesystem",
        name="Local FS",
        capabilities=("file.read",),
        availability=AvailabilityStatus.AVAILABLE,
    )
    await provider_registry.register(prov)

    # Run discovery on local node
    local_node = await ecosystem_service.discover_local_node()

    assert local_node.node_id == str(sample_identity.node_id)
    assert local_node.node_name == "test-shyam-node"
    assert local_node.is_local is True
    assert local_node.state == EcosystemNodeState.AVAILABLE
    assert "local.filesystem" in local_node.providers
    assert "file.read" in local_node.capability_ids
    assert local_node.providers["local.filesystem"].capabilities[0].name == "Read Files"


@pytest.mark.asyncio
async def test_ingest_udp_peer(ecosystem_service):
    peer_id = uuid4()
    udp_peer = Peer(
        node_id=peer_id,
        node_name="remote-peer-1",
        address="192.168.1.50",
        port=54321,
    )

    node = await ecosystem_service.ingest_udp_peer(udp_peer)
    assert node.node_id == str(peer_id)
    assert node.node_name == "remote-peer-1"
    assert node.is_local is False
    assert node.state == EcosystemNodeState.AVAILABLE
    assert "shyam.peer" in node.providers
    assert "shyam.runtime.inspect" in node.capability_ids

    # Lost notification
    await ecosystem_service.handle_udp_peer_lost(peer_id)
    updated = ecosystem_service.registry.get_node(str(peer_id))
    assert updated.state == EcosystemNodeState.UNAVAILABLE


@pytest.mark.asyncio
async def test_ingest_flux_peers(sample_identity, provider_registry, capability_registry):
    mock_flux = MagicMock()
    mock_flux.is_connected = True
    mock_flux.descriptor = Provider(
        provider_id="flux.gateway",
        name="Flux Gateway",
        capabilities=("flux.transfer",),
    )
    mock_flux.capability_definitions = (
        Capability(
            capability_id="flux.transfer",
            name="Flux Data Transfer",
        ),
    )
    mock_flux.discover_peers.return_value = [
        FluxPeerInfo(
            peer_id="12D3KooWPeerA",
            address="/ip4/192.168.1.10/tcp/9000",
            connectivity="reachable",
        ),
        FluxPeerInfo(
            peer_id="12D3KooWPeerB",
            address="/ip4/192.168.1.11/tcp/9000",
            connectivity="unreachable",
        ),
    ]

    service = EcosystemDiscoveryService(
        local_identity=sample_identity,
        provider_registry=provider_registry,
        capability_registry=capability_registry,
        flux_provider=mock_flux,
    )

    flux_nodes = await service.ingest_flux_peers()
    assert len(flux_nodes) == 2

    # Node A is reachable -> AVAILABLE
    assert flux_nodes[0].node_id == "flux:12D3KooWPeerA"
    assert flux_nodes[0].state == EcosystemNodeState.AVAILABLE

    # Node B is unreachable -> UNAVAILABLE
    assert flux_nodes[1].node_id == "flux:12D3KooWPeerB"
    assert flux_nodes[1].state == EcosystemNodeState.UNAVAILABLE


@pytest.mark.asyncio
async def test_full_discover_snapshot(sample_identity, provider_registry, capability_registry):
    service = EcosystemDiscoveryService(
        local_identity=sample_identity,
        provider_registry=provider_registry,
        capability_registry=capability_registry,
    )

    snapshot = await service.discover()
    assert snapshot.local_node_id == str(sample_identity.node_id)
    assert snapshot.total_nodes == 1
    assert len(snapshot.active_nodes) == 1
