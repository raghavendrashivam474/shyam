"""Ecosystem Discovery Domain Models - S8.

Provides normalized, provider-independent representations of nodes,
providers, and capabilities across the Shyam computing ecosystem.

Decoupled from specific provider protocols (Zarya EIP-1, Flux Gateway, UDP).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.events.bus import Event
from shyam.providers.model import Provider


class EcosystemNodeState(StrEnum):
    """Normalized lifecycle/reachability state for an ecosystem node."""

    KNOWN = "known"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    STALE = "stale"


class DiscoveredCapability(BaseModel):
    """Normalized representation of a capability exposed by a discovered provider."""

    model_config = ConfigDict(frozen=True)

    capability_id: str = Field(description="Namespaced capability ID (e.g. 'file.read')")
    name: str = Field(default="", description="Human-readable name")
    version: str = Field(default="1.0.0", description="Semantic version string")
    description: str = Field(default="", description="Capability description")
    availability: AvailabilityStatus = Field(
        default=AvailabilityStatus.AVAILABLE,
        description="Current capability availability status",
    )

    @classmethod
    def from_capability(cls, cap: Capability) -> DiscoveredCapability:
        """Create a DiscoveredCapability from a Shyam core Capability model."""
        return cls(
            capability_id=cap.capability_id,
            name=cap.name,
            version=cap.version,
            description=cap.description,
            availability=cap.availability,
        )


class DiscoveredProvider(BaseModel):
    """Normalized representation of a provider residing on an ecosystem node."""

    model_config = ConfigDict(frozen=True)

    provider_id: str = Field(description="Namespaced provider ID (e.g. 'local.filesystem')")
    name: str = Field(description="Human-readable provider name")
    version: str = Field(default="1.0.0", description="Provider version")
    description: str = Field(default="", description="Provider description")
    capabilities: tuple[DiscoveredCapability, ...] = Field(
        default_factory=tuple,
        description="Capabilities exposed by this provider",
    )
    status: AvailabilityStatus = Field(
        default=AvailabilityStatus.AVAILABLE,
        description="Current provider availability status",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific public metadata",
    )
    last_seen: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when provider was last confirmed active",
    )

    @property
    def capability_ids(self) -> tuple[str, ...]:
        """Return tuple of capability IDs exposed by this provider."""
        return tuple(c.capability_id for c in self.capabilities)

    @classmethod
    def from_provider(
        cls,
        provider: Provider,
        capability_models: tuple[Capability, ...] | None = None,
        last_seen: datetime | None = None,
    ) -> DiscoveredProvider:
        """Create a DiscoveredProvider from a Shyam Provider model and capability models."""
        caps: list[DiscoveredCapability] = []
        if capability_models:
            for cap in capability_models:
                caps.append(DiscoveredCapability.from_capability(cap))
        else:
            for cid in provider.capabilities:
                caps.append(DiscoveredCapability(capability_id=cid, name=cid))

        return cls(
            provider_id=provider.provider_id,
            name=provider.name,
            version=provider.version,
            description=provider.description,
            capabilities=tuple(caps),
            status=provider.availability,
            metadata=dict(provider.metadata),
            last_seen=last_seen or datetime.now(UTC),
        )


class DiscoveredNode(BaseModel):
    """Normalized representation of a computing node in the Shyam ecosystem."""

    model_config = ConfigDict(frozen=True)

    node_id: str = Field(
        description="Unique identifier of the node (string or UUID string)",
    )
    node_name: str = Field(
        description="Human-readable name of the node",
    )
    state: EcosystemNodeState = Field(
        default=EcosystemNodeState.KNOWN,
        description="Current normalized state of the node",
    )
    is_local: bool = Field(
        default=False,
        description="True if this node represents the local executing Shyam instance",
    )
    protocol_version: str = Field(
        default="1.0.0",
        description="Protocol version announced or negotiated with the node",
    )
    providers: dict[str, DiscoveredProvider] = Field(
        default_factory=dict,
        description="Mapping of provider_id to DiscoveredProvider on this node",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Ecosystem metadata (e.g. transport, address, origin)",
    )
    first_seen: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when this node was first observed",
    )
    last_seen: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when this node was most recently observed",
    )

    def with_touch(self, seen_at: datetime | None = None) -> DiscoveredNode:
        """Return a copy with updated last_seen timestamp."""
        return self.model_copy(update={"last_seen": seen_at or datetime.now(UTC)})

    def with_state(self, state: EcosystemNodeState) -> DiscoveredNode:
        """Return a copy with updated state."""
        return self.model_copy(update={"state": state})

    def with_provider(self, provider: DiscoveredProvider) -> DiscoveredNode:
        """Return a copy with an added or updated provider."""
        new_providers = dict(self.providers)
        new_providers[provider.provider_id] = provider
        return self.model_copy(update={"providers": new_providers})

    def without_provider(self, provider_id: str) -> DiscoveredNode:
        """Return a copy with a provider removed."""
        new_providers = {k: v for k, v in self.providers.items() if k != provider_id}
        return self.model_copy(update={"providers": new_providers})

    @property
    def capability_ids(self) -> set[str]:
        """Set of all capability IDs available across all providers on this node."""
        caps: set[str] = set()
        for prov in self.providers.values():
            caps.update(prov.capability_ids)
        return caps


class EcosystemSnapshot(BaseModel):
    """Point-in-time snapshot of the entire discovered ecosystem."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Snapshot capture timestamp",
    )
    local_node_id: str = Field(
        description="Node ID of the local Shyam node",
    )
    nodes: dict[str, DiscoveredNode] = Field(
        default_factory=dict,
        description="Map of node_id to DiscoveredNode",
    )

    @property
    def total_nodes(self) -> int:
        """Total number of known nodes in this snapshot."""
        return len(self.nodes)

    @property
    def active_nodes(self) -> list[DiscoveredNode]:
        """List of nodes that are currently AVAILABLE."""
        return [n for n in self.nodes.values() if n.state == EcosystemNodeState.AVAILABLE]

    @property
    def total_providers(self) -> int:
        """Total number of providers across all nodes."""
        return sum(len(n.providers) for n in self.nodes.values())

    @property
    def all_capabilities(self) -> set[str]:
        """Set of all unique capability IDs across all nodes."""
        caps: set[str] = set()
        for n in self.nodes.values():
            caps.update(n.capability_ids)
        return caps


# --- Ecosystem Discovery Events ---


class EcosystemNodeDiscoveredEvent(Event):
    """Fired when a new ecosystem node is discovered."""

    node: DiscoveredNode


class EcosystemNodeUpdatedEvent(Event):
    """Fired when a known ecosystem node's state, providers, or metadata change."""

    node: DiscoveredNode
    previous_state: EcosystemNodeState | None = None


class EcosystemNodeStaleEvent(Event):
    """Fired when a node has not been observed within the freshness window."""

    node_id: str
    node_name: str
    last_seen: datetime


class EcosystemNodeLostEvent(Event):
    """Fired when a node is confirmed removed or lost from the ecosystem."""

    node_id: str
    node_name: str
    last_seen: datetime
