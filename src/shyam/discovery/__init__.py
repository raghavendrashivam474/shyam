"""Shyam Discovery Subsystem.

Combines low-level UDP peer discovery (S2) with normalized
Ecosystem Discovery (S8) across nodes, providers, and capabilities.
"""

from shyam.discovery.ecosystem_models import (
    DiscoveredCapability,
    DiscoveredNode,
    DiscoveredProvider,
    EcosystemNodeDiscoveredEvent,
    EcosystemNodeLostEvent,
    EcosystemNodeStaleEvent,
    EcosystemNodeState,
    EcosystemNodeUpdatedEvent,
    EcosystemSnapshot,
)
from shyam.discovery.ecosystem_registry import EcosystemRegistry
from shyam.discovery.ecosystem_service import EcosystemDiscoveryService
from shyam.discovery.model import (
    NodeIdentityReadyEvent,
    Peer,
    PeerDiscoveredEvent,
    PeerLostEvent,
    PeerUpdatedEvent,
)
from shyam.discovery.service import DiscoveryService

__all__ = [
    # S2 Low-level UDP Discovery
    "DiscoveryService",
    "NodeIdentityReadyEvent",
    "Peer",
    "PeerDiscoveredEvent",
    "PeerLostEvent",
    "PeerUpdatedEvent",
    # S8 Normalized Ecosystem Discovery Models
    "DiscoveredCapability",
    "DiscoveredNode",
    "DiscoveredProvider",
    "EcosystemNodeState",
    "EcosystemSnapshot",
    # S8 Ecosystem Events
    "EcosystemNodeDiscoveredEvent",
    "EcosystemNodeLostEvent",
    "EcosystemNodeStaleEvent",
    "EcosystemNodeUpdatedEvent",
    # S8 Registry & Service
    "EcosystemRegistry",
    "EcosystemDiscoveryService",
]
