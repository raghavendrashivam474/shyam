"""Test discovery module public exports."""

import shyam.discovery as disc


def test_discovery_exports():
    # S2
    assert hasattr(disc, "DiscoveryService")
    assert hasattr(disc, "Peer")
    assert hasattr(disc, "NodeIdentityReadyEvent")
    assert hasattr(disc, "PeerDiscoveredEvent")
    assert hasattr(disc, "PeerLostEvent")
    assert hasattr(disc, "PeerUpdatedEvent")

    # S8
    assert hasattr(disc, "DiscoveredCapability")
    assert hasattr(disc, "DiscoveredProvider")
    assert hasattr(disc, "DiscoveredNode")
    assert hasattr(disc, "EcosystemNodeState")
    assert hasattr(disc, "EcosystemSnapshot")
    assert hasattr(disc, "EcosystemRegistry")
    assert hasattr(disc, "EcosystemDiscoveryService")
    assert hasattr(disc, "EcosystemNodeDiscoveredEvent")
    assert hasattr(disc, "EcosystemNodeUpdatedEvent")
    assert hasattr(disc, "EcosystemNodeStaleEvent")
    assert hasattr(disc, "EcosystemNodeLostEvent")
