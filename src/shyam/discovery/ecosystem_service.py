"""Ecosystem Discovery Service (S8).

Normalizes local providers (S5 Fabric, S6 Zarya, S7 Flux) and remote UDP peers
into unified DiscoveredNode and DiscoveredProvider domain models.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

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
from shyam.discovery.model import Peer
from shyam.events.bus import EventBus
from shyam.providers.flux.models import FluxPeerInfo
from shyam.providers.flux.provider import FluxProvider
from shyam.providers.model import Provider
from shyam.providers.registry import ProviderRegistry
from shyam.providers.zarya.provider import ZaryaProvider

if TYPE_CHECKING:
    from shyam.identity import NodeIdentity

logger = logging.getLogger(__name__)


class EcosystemDiscoveryService:
    """Aggregates local provider fabric state, sovereign Zarya capabilities,
    Flux gateway transports, and remote UDP announcements into the Ecosystem Registry.
    """

    def __init__(
        self,
        local_identity: NodeIdentity,
        provider_registry: ProviderRegistry,
        capability_registry: CapabilityRegistry,
        ecosystem_registry: EcosystemRegistry | None = None,
        zarya_provider: ZaryaProvider | None = None,
        flux_provider: FluxProvider | None = None,
        event_bus: EventBus | None = None,
        stale_threshold_secs: float = 30.0,
    ) -> None:
        self.local_identity = local_identity
        self.local_node_id = str(local_identity.node_id)
        self.providers = provider_registry
        self.capabilities = capability_registry
        self.registry = ecosystem_registry or EcosystemRegistry(event_bus=event_bus)
        self.zarya_provider = zarya_provider
        self.flux_provider = flux_provider
        self._event_bus = event_bus
        self.stale_threshold_secs = stale_threshold_secs

    # -------------------------------------------------------------------------
    # Local Node Normalization
    # -------------------------------------------------------------------------

    async def discover_local_node(self) -> DiscoveredNode:
        """Collect and normalize local node providers and capabilities."""
        node_id = self.local_node_id
        node_name = self.local_identity.node_name
        now = datetime.now(UTC)

        # 1. Collect all local providers from ProviderRegistry
        discovered_providers: dict[str, DiscoveredProvider] = {}

        for prov in self.providers.list_all():
            # Resolve full Capability definitions from CapabilityRegistry
            cap_models: list[Capability] = []
            for cid in prov.capabilities:
                cap_def = self.capabilities.get(cid)
                if cap_def:
                    cap_models.append(cap_def)
                else:
                    # Fabric or provider referenced a cap without explicit definition
                    cap_models.append(
                        Capability(
                            capability_id=cid,
                            name=cid,
                            availability=prov.availability,
                        )
                    )

            disc_prov = DiscoveredProvider.from_provider(
                provider=prov,
                capability_models=tuple(cap_models),
                last_seen=now,
            )
            discovered_providers[prov.provider_id] = disc_prov

        # 2. Check Zarya if connected and not already in providers registry
        if self.zarya_provider and self.zarya_provider.is_connected:
            z_desc = self.zarya_provider.descriptor
            if z_desc and z_desc.provider_id not in discovered_providers:
                z_caps = self.zarya_provider.capability_definitions
                discovered_providers[z_desc.provider_id] = DiscoveredProvider.from_provider(
                    provider=z_desc,
                    capability_models=z_caps,
                    last_seen=now,
                )

        # 3. Check Flux if connected and not already in providers registry
        if self.flux_provider and self.flux_provider.is_connected:
            f_desc = self.flux_provider.descriptor
            if f_desc and f_desc.provider_id not in discovered_providers:
                f_caps = self.flux_provider.capability_definitions
                discovered_providers[f_desc.provider_id] = DiscoveredProvider.from_provider(
                    provider=f_desc,
                    capability_models=f_caps,
                    last_seen=now,
                )

        existing_node = self.registry.get_node(node_id)
        first_seen = existing_node.first_seen if existing_node else now

        local_node = DiscoveredNode(
            node_id=node_id,
            node_name=node_name,
            state=EcosystemNodeState.AVAILABLE,
            is_local=True,
            protocol_version=self.local_identity.protocol_version,
            providers=discovered_providers,
            metadata={"environment": "local"},
            first_seen=first_seen,
            last_seen=now,
        )

        await self.registry.register_node(local_node, overwrite=True)
        return local_node

    # -------------------------------------------------------------------------
    # Remote Peer Ingestion
    # -------------------------------------------------------------------------

    async def ingest_flux_peers(self) -> list[DiscoveredNode]:
        """Poll Flux Gateway peer discovery and normalize peers as ecosystem nodes."""
        if not self.flux_provider or not self.flux_provider.is_connected:
            return []

        try:
            flux_peers: list[FluxPeerInfo] = self.flux_provider.discover_peers()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to discover peers via Flux Gateway: %s", exc)
            return []

        ingested: list[DiscoveredNode] = []
        now = datetime.now(UTC)

        for peer in flux_peers:
            node_id = f"flux:{peer.peer_id}"
            node_name = f"flux-peer-{peer.peer_id[:8]}"

            # Map connectivity string to EcosystemNodeState
            state = EcosystemNodeState.KNOWN
            if peer.connectivity == "reachable":
                state = EcosystemNodeState.AVAILABLE
            elif peer.connectivity == "unreachable":
                state = EcosystemNodeState.UNAVAILABLE

            existing = self.registry.get_node(node_id)
            first_seen = existing.first_seen if existing else now

            # Peer advertises basic flux transport capabilities by default
            flux_cap = DiscoveredCapability(
                capability_id="flux.transfer",
                name="Flux Data Transfer",
                availability=AvailabilityStatus.AVAILABLE if state == EcosystemNodeState.AVAILABLE else AvailabilityStatus.UNAVAILABLE,
            )
            peer_prov = DiscoveredProvider(
                provider_id="flux.peer",
                name="Flux Peer Connectivity",
                version="1.0.0",
                capabilities=(flux_cap,),
                status=AvailabilityStatus.AVAILABLE if state == EcosystemNodeState.AVAILABLE else AvailabilityStatus.UNAVAILABLE,
                metadata={"paths_count": len(peer.paths), "connectivity": peer.connectivity},
                last_seen=now,
            )

            peer_node = DiscoveredNode(
                node_id=node_id,
                node_name=node_name,
                state=state,
                is_local=False,
                protocol_version="1.0.0",
                providers={"flux.peer": peer_prov},
                metadata={
                    "origin": "flux_gateway",
                    "flux_peer_id": peer.peer_id,
                    "address": peer.address,
                    "connectivity": peer.connectivity,
                },
                first_seen=first_seen,
                last_seen=now,
            )

            await self.registry.register_node(peer_node, overwrite=True)
            ingested.append(peer_node)

        return ingested

    async def ingest_udp_peer(self, peer: Peer) -> DiscoveredNode:
        """Normalize a UDP-discovered Shyam Peer into an ecosystem node."""
        node_id = str(peer.node_id)
        now = datetime.now(UTC)

        existing = self.registry.get_node(node_id)
        first_seen = existing.first_seen if existing else peer.discovered_at

        # Remote Shyam peer offers runtime inspect capability
        capabilities = [
            DiscoveredCapability(
                capability_id="shyam.runtime.inspect",
                name="Runtime Introspection",
                availability=AvailabilityStatus.AVAILABLE,
            )
        ]

        # If peer advertises zarya_url or zarya capabilities, add continuity capability
        providers_map: dict[str, DiscoveredProvider] = {}
        if peer.metadata.get("zarya_url") or peer.metadata.get("has_zarya"):
            zarya_cap = DiscoveredCapability(
                capability_id="zarya.work.continue",
                name="Zarya Work Continuation",
                availability=AvailabilityStatus.AVAILABLE,
            )
            zarya_prov = DiscoveredProvider(
                provider_id="zarya.agent",
                name="Zarya Agent Provider",
                version="1.0.0",
                capabilities=(zarya_cap,),
                status=AvailabilityStatus.AVAILABLE,
                metadata={
                    "zarya_url": peer.metadata.get("zarya_url"),
                },
                last_seen=peer.last_seen,
            )
            providers_map["zarya.agent"] = zarya_prov

        peer_prov = DiscoveredProvider(
            provider_id="shyam.peer",
            name="Remote Shyam Node",
            version=peer.protocol_version,
            capabilities=tuple(capabilities),
            status=AvailabilityStatus.AVAILABLE,
            metadata={"address": peer.address, "port": peer.port},
            last_seen=peer.last_seen,
        )
        providers_map["shyam.peer"] = peer_prov

        disc_node = DiscoveredNode(
            node_id=node_id,
            node_name=peer.node_name,
            state=EcosystemNodeState.AVAILABLE,
            is_local=False,
            protocol_version=peer.protocol_version,
            providers=providers_map,
            metadata={
                "origin": "udp_broadcast",
                "address": peer.address,
                "port": peer.port,
                **peer.metadata,
            },
            first_seen=first_seen,
            last_seen=peer.last_seen,
        )

        await self.registry.register_node(disc_node, overwrite=True)
        return disc_node

    async def handle_udp_peer_lost(self, node_id: UUID) -> None:
        """Mark a lost UDP peer as UNAVAILABLE in the registry."""
        node_id_str = str(node_id)
        node = self.registry.get_node(node_id_str)
        if node and not node.is_local:
            updated = node.with_state(EcosystemNodeState.UNAVAILABLE)
            await self.registry.register_node(updated, overwrite=True)

    # -------------------------------------------------------------------------
    # High-level Orchestration
    # -------------------------------------------------------------------------

    async def discover(self) -> EcosystemSnapshot:
        """Refresh and retrieve current unified ecosystem snapshot.

        1. Normalizes local node and providers.
        2. Ingests reachable Flux Gateway peers.
        3. Returns frozen snapshot.
        """
        await self.discover_local_node()

        if self.flux_provider and self.flux_provider.is_connected:
            await self.ingest_flux_peers()

        return self.registry.create_snapshot(local_node_id=self.local_node_id)
