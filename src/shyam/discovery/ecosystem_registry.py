"""In-memory Ecosystem Discovery Registry - S8.

Maintains normalized representations of all known nodes, providers,
and capabilities across the local computing ecosystem.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from shyam.events.bus import EventBus

logger = logging.getLogger("shyam.discovery.registry")


class EcosystemRegistry:
    """Thread-safe in-memory registry of discovered ecosystem nodes."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._nodes: dict[str, DiscoveredNode] = {}
        self._lock = asyncio.Lock()
        self._event_bus: EventBus | None = event_bus

    @property
    def count(self) -> int:
        """Return the count of known nodes."""
        return len(self._nodes)

    def contains(self, node_id: str) -> bool:
        """Check if a node ID is registered."""
        return node_id in self._nodes

    def __contains__(self, node_id: str) -> bool:
        return self.contains(node_id)

    async def register_node(
        self,
        node: DiscoveredNode,
        *,
        overwrite: bool = True,
    ) -> DiscoveredNode:
        """Register or update a discovered node.

        Args:
            node: The DiscoveredNode instance.
            overwrite: If True (default), updates existing node record.

        Returns:
            The registered DiscoveredNode instance.
        """
        async with self._lock:
            node_id = node.node_id
            existing = self._nodes.get(node_id)

            if existing is not None and not overwrite:
                return existing

            is_new = existing is None
            prev_state = existing.state if existing else None
            self._nodes[node_id] = node

            logger.info(
                "%s ecosystem node: %s (%s) [state=%s, providers=%d]",
                "Discovered new" if is_new else "Updated",
                node.node_name,
                node_id,
                node.state.value,
                len(node.providers),
            )

        # Publish event outside lock
        if self._event_bus:
            if is_new:
                await self._event_bus.publish(
                    EcosystemNodeDiscoveredEvent(node=node)
                )
            else:
                await self._event_bus.publish(
                    EcosystemNodeUpdatedEvent(
                        node=node,
                        previous_state=prev_state,
                    )
                )

        return node

    async def touch_node(
        self,
        node_id: str,
        seen_at: datetime | None = None,
    ) -> DiscoveredNode | None:
        """Update last_seen timestamp for an existing node."""
        async with self._lock:
            existing = self._nodes.get(node_id)
            if existing is None:
                return None
            updated = existing.with_touch(seen_at=seen_at)
            # If node was stale, touching it transitions back to AVAILABLE (or KNOWN)
            if updated.state == EcosystemNodeState.STALE:
                updated = updated.with_state(EcosystemNodeState.AVAILABLE)
            self._nodes[node_id] = updated

        return updated

    async def update_node_state(
        self,
        node_id: str,
        state: EcosystemNodeState,
    ) -> DiscoveredNode | None:
        """Update the lifecycle/reachability state of a node."""
        async with self._lock:
            existing = self._nodes.get(node_id)
            if existing is None:
                return None
            prev_state = existing.state
            if prev_state == state:
                return existing
            updated = existing.with_state(state)
            self._nodes[node_id] = updated

        if self._event_bus:
            await self._event_bus.publish(
                EcosystemNodeUpdatedEvent(
                    node=updated,
                    previous_state=prev_state,
                )
            )

        return updated

    async def add_provider(
        self,
        node_id: str,
        provider: DiscoveredProvider,
    ) -> DiscoveredNode | None:
        """Add or update a provider on a given node."""
        async with self._lock:
            existing = self._nodes.get(node_id)
            if existing is None:
                return None
            updated = existing.with_provider(provider)
            self._nodes[node_id] = updated

        if self._event_bus:
            await self._event_bus.publish(
                EcosystemNodeUpdatedEvent(
                    node=updated,
                    previous_state=existing.state,
                )
            )

        return updated

    async def remove_provider(
        self,
        node_id: str,
        provider_id: str,
    ) -> DiscoveredNode | None:
        """Remove a provider from a given node."""
        async with self._lock:
            existing = self._nodes.get(node_id)
            if existing is None:
                return None
            if provider_id not in existing.providers:
                return existing
            updated = existing.without_provider(provider_id)
            self._nodes[node_id] = updated

        if self._event_bus:
            await self._event_bus.publish(
                EcosystemNodeUpdatedEvent(
                    node=updated,
                    previous_state=existing.state,
                )
            )

        return updated

    async def remove_node(self, node_id: str) -> DiscoveredNode | None:
        """Remove a node from the registry."""
        async with self._lock:
            removed = self._nodes.pop(node_id, None)

        if removed and self._event_bus:
            await self._event_bus.publish(
                EcosystemNodeLostEvent(
                    node_id=removed.node_id,
                    node_name=removed.node_name,
                    last_seen=removed.last_seen,
                )
            )

        return removed

    def get_node(self, node_id: str) -> DiscoveredNode | None:
        """Get a node by ID."""
        return self._nodes.get(node_id)

    def get_local_node(self) -> DiscoveredNode | None:
        """Get the node designated as local."""
        for node in self._nodes.values():
            if node.is_local:
                return node
        return None

    def list_nodes(
        self,
        state: EcosystemNodeState | None = None,
    ) -> list[DiscoveredNode]:
        """List all registered nodes, optionally filtering by state."""
        if state is None:
            return list(self._nodes.values())
        return [n for n in self._nodes.values() if n.state == state]

    def find_nodes_by_capability(self, capability_id: str) -> list[DiscoveredNode]:
        """Find all nodes that offer a given capability ID."""
        return [n for n in self._nodes.values() if capability_id in n.capability_ids]

    def find_nodes_by_provider(self, provider_id: str) -> list[DiscoveredNode]:
        """Find all nodes that host a given provider ID."""
        return [n for n in self._nodes.values() if provider_id in n.providers]

    async def reconcile_stale(
        self,
        stale_threshold_secs: float,
        current_time: datetime | None = None,
    ) -> list[str]:
        """Mark nodes as STALE if they haven't been observed within the threshold.

        Local nodes are exempted from automatic staleness.

        Returns:
            List of node_ids marked stale in this run.
        """
        now = current_time or datetime.now(UTC)
        stale_node_ids: list[str] = []
        events_to_emit: list[tuple[str, str, datetime]] = []

        async with self._lock:
            for node_id, node in self._nodes.items():
                if node.is_local:
                    continue
                if node.state in (EcosystemNodeState.AVAILABLE, EcosystemNodeState.KNOWN):
                    delta = (now - node.last_seen).total_seconds()
                    if delta > stale_threshold_secs:
                        updated = node.with_state(EcosystemNodeState.STALE)
                        self._nodes[node_id] = updated
                        stale_node_ids.append(node_id)
                        events_to_emit.append((node.node_id, node.node_name, node.last_seen))

        if self._event_bus:
            for n_id, n_name, l_seen in events_to_emit:
                await self._event_bus.publish(
                    EcosystemNodeStaleEvent(
                        node_id=n_id,
                        node_name=n_name,
                        last_seen=l_seen,
                    )
                )

        return stale_node_ids

    def create_snapshot(self, local_node_id: str = "") -> EcosystemSnapshot:
        """Produce an immutable point-in-time snapshot of the ecosystem."""
        local_id = local_node_id
        if not local_id:
            loc = self.get_local_node()
            local_id = loc.node_id if loc else "unknown"

        return EcosystemSnapshot(
            local_node_id=local_id,
            nodes=dict(self._nodes),
        )
