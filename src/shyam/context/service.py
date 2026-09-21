"""Ecosystem Context Service - S12.

Coordinates background state aggregation by wiring S8 ecosystem events
and S10 workflow lifecycle events directly to the EcosystemStateStore.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from shyam.discovery.ecosystem_models import (
    EcosystemNodeDiscoveredEvent,
    EcosystemNodeLostEvent,
    EcosystemNodeStaleEvent,
    EcosystemNodeUpdatedEvent,
)
from shyam.workflow.events import (
    WorkflowCancelledEvent,
    WorkflowCompletedEvent,
    WorkflowFailedEvent,
    WorkflowStartedEvent,
    WorkflowStepStartedEvent,
)

if TYPE_CHECKING:
    from shyam.context.store import EcosystemStateStore
    from shyam.discovery.ecosystem_registry import EcosystemRegistry
    from shyam.events.bus import EventBus

logger = logging.getLogger("shyam.context.service")


class EcosystemContextService:
    """Coordinates ecosystem state aggregation and provides situational context."""

    def __init__(
        self,
        registry: EcosystemRegistry,
        event_bus: EventBus,
        store: EcosystemStateStore,
    ) -> None:
        self._registry = registry
        self._events = event_bus
        self._store = store
        self._subscribed = False

    async def start(self) -> None:
        """Start the context service, sync initial snapshot, and subscribe to events."""
        if self._subscribed:
            return

        # Perform initial sync of discovery facts
        await self._sync_snapshot()

        # Subscribe store handlers to workflow events
        await self._events.subscribe(WorkflowStartedEvent, self._store.on_workflow_started)
        await self._events.subscribe(WorkflowCompletedEvent, self._store.on_workflow_completed)
        await self._events.subscribe(WorkflowFailedEvent, self._store.on_workflow_failed)
        await self._events.subscribe(WorkflowCancelledEvent, self._store.on_workflow_cancelled)
        await self._events.subscribe(WorkflowStepStartedEvent, self._store.on_step_started)

        # Subscribe to local discovery events (via wrapper handlers that also sync snapshots)
        await self._events.subscribe(EcosystemNodeDiscoveredEvent, self._on_node_discovered)
        await self._events.subscribe(EcosystemNodeUpdatedEvent, self._on_node_updated)
        await self._events.subscribe(EcosystemNodeStaleEvent, self._on_node_stale)
        await self._events.subscribe(EcosystemNodeLostEvent, self._on_node_lost)

        self._subscribed = True
        logger.info("EcosystemContextService started and subscribed to EventBus.")

    async def stop(self) -> None:
        """Unsubscribe from all events and stop the service."""
        if not self._subscribed:
            return

        await self._events.unsubscribe(WorkflowStartedEvent, self._store.on_workflow_started)
        await self._events.unsubscribe(WorkflowCompletedEvent, self._store.on_workflow_completed)
        await self._events.unsubscribe(WorkflowFailedEvent, self._store.on_workflow_failed)
        await self._events.unsubscribe(WorkflowCancelledEvent, self._store.on_workflow_cancelled)
        await self._events.unsubscribe(WorkflowStepStartedEvent, self._store.on_step_started)

        await self._events.unsubscribe(EcosystemNodeDiscoveredEvent, self._on_node_discovered)
        await self._events.unsubscribe(EcosystemNodeUpdatedEvent, self._on_node_updated)
        await self._events.unsubscribe(EcosystemNodeStaleEvent, self._on_node_stale)
        await self._events.unsubscribe(EcosystemNodeLostEvent, self._on_node_lost)

        self._subscribed = False
        logger.info("EcosystemContextService stopped and unsubscribed.")

    async def _sync_snapshot(self) -> None:
        """Query S8 registry to get the most authoritative ecosystem snapshot and update store."""
        snapshot = self._registry.create_snapshot()
        await self._store.update_discovery(snapshot)

    async def _on_node_discovered(self, event: EcosystemNodeDiscoveredEvent) -> None:
        await self._store.on_node_discovered(event)
        await self._sync_snapshot()

    async def _on_node_updated(self, event: EcosystemNodeUpdatedEvent) -> None:
        await self._store.on_node_updated(event)
        await self._sync_snapshot()

    async def _on_node_stale(self, event: EcosystemNodeStaleEvent) -> None:
        await self._store.on_node_stale(event)
        await self._sync_snapshot()

    async def _on_node_lost(self, event: EcosystemNodeLostEvent) -> None:
        await self._store.on_node_lost(event)
        await self._sync_snapshot()
