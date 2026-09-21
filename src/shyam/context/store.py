"""In-memory Ecosystem State Store - S12.

Aggregates S8 discovery snapshots and S10 workflow lifecycle events
into a unified EcosystemState. Produces immutable snapshots on read.

This is NOT a second source of truth for discovery. It observes and
indexes state derived from existing subsystems.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import UTC, datetime

from shyam.context.models import (
    ActiveWorkItem,
    ActivityKind,
    EcosystemContext,
    EcosystemState,
    RecentActivityEntry,
    WorkStatus,
)
from shyam.discovery.ecosystem_models import (
    EcosystemNodeDiscoveredEvent,
    EcosystemNodeLostEvent,
    EcosystemNodeStaleEvent,
    EcosystemNodeUpdatedEvent,
    EcosystemSnapshot,
)
from shyam.workflow.events import (
    WorkflowCancelledEvent,
    WorkflowCompletedEvent,
    WorkflowFailedEvent,
    WorkflowStartedEvent,
    WorkflowStepStartedEvent,
)

logger = logging.getLogger("shyam.context.store")

# Maximum number of recent activity entries to retain in memory.
_MAX_ACTIVITY_ENTRIES = 100


class EcosystemStateStore:
    """Thread-safe in-memory aggregator of ecosystem state.

    Observes S8 discovery snapshots and S10 workflow events to maintain
    a unified view. All reads return frozen EcosystemState snapshots.
    """

    def __init__(self, max_activity: int = _MAX_ACTIVITY_ENTRIES) -> None:
        self._lock = asyncio.Lock()
        self._version: int = 0

        # Latest S8 discovery snapshot (set via update_discovery)
        self._discovery: EcosystemSnapshot | None = None

        # Active work indexed by workflow_id
        self._active_work: dict[str, ActiveWorkItem] = {}

        # Recent activity ring buffer (newest first when snapshotted)
        self._activity: deque[RecentActivityEntry] = deque(maxlen=max_activity)

    # ------------------------------------------------------------------
    # Discovery integration
    # ------------------------------------------------------------------

    async def update_discovery(self, snapshot: EcosystemSnapshot) -> None:
        """Ingest a fresh S8 EcosystemSnapshot as the discovery baseline."""
        async with self._lock:
            self._discovery = snapshot
            self._version += 1
        logger.debug(
            "State store discovery updated (v%d, %d nodes).",
            self._version,
            snapshot.total_nodes,
        )

    # ------------------------------------------------------------------
    # Workflow event handlers (subscribe these to the EventBus)
    # ------------------------------------------------------------------

    async def on_workflow_started(self, event: WorkflowStartedEvent) -> None:
        """Track a newly started workflow."""
        item = ActiveWorkItem(
            workflow_id=event.workflow_id,
            workflow_name=event.workflow_name,
            status=WorkStatus.RUNNING,
            step_count=event.step_count,
            started_at=event.timestamp,
        )
        activity = RecentActivityEntry(
            kind=ActivityKind.WORKFLOW_STARTED,
            description=f"Workflow '{event.workflow_name}' started ({event.step_count} steps).",
            occurred_at=event.timestamp,
            related_workflow_id=event.workflow_id,
        )
        async with self._lock:
            self._active_work[event.workflow_id] = item
            self._activity.appendleft(activity)
            self._version += 1

    async def on_workflow_completed(self, event: WorkflowCompletedEvent) -> None:
        """Mark a workflow as completed."""
        activity = RecentActivityEntry(
            kind=ActivityKind.WORKFLOW_COMPLETED,
            description=f"Workflow '{event.workflow_name}' completed.",
            occurred_at=event.timestamp,
            related_workflow_id=event.workflow_id,
        )
        async with self._lock:
            existing = self._active_work.pop(event.workflow_id, None)
            if existing:
                self._active_work[event.workflow_id] = existing.model_copy(
                    update={
                        "status": WorkStatus.COMPLETED,
                        "completed_steps": event.completed_steps_count,
                        "finished_at": event.timestamp,
                    }
                )
                # Immediately remove from active since it's terminal
                del self._active_work[event.workflow_id]
            self._activity.appendleft(activity)
            self._version += 1

    async def on_workflow_failed(self, event: WorkflowFailedEvent) -> None:
        """Mark a workflow as failed."""
        activity = RecentActivityEntry(
            kind=ActivityKind.WORKFLOW_FAILED,
            description=f"Workflow '{event.workflow_name}' failed: {event.error}",
            occurred_at=event.timestamp,
            related_workflow_id=event.workflow_id,
        )
        async with self._lock:
            self._active_work.pop(event.workflow_id, None)
            self._activity.appendleft(activity)
            self._version += 1

    async def on_workflow_cancelled(self, event: WorkflowCancelledEvent) -> None:
        """Mark a workflow as cancelled."""
        activity = RecentActivityEntry(
            kind=ActivityKind.WORKFLOW_CANCELLED,
            description=f"Workflow '{event.workflow_name}' cancelled: {event.reason}",
            occurred_at=event.timestamp,
            related_workflow_id=event.workflow_id,
        )
        async with self._lock:
            self._active_work.pop(event.workflow_id, None)
            self._activity.appendleft(activity)
            self._version += 1

    async def on_step_started(self, event: WorkflowStepStartedEvent) -> None:
        """Enrich active work with target node/provider from step resolution."""
        if event.target is None:
            return
        async with self._lock:
            existing = self._active_work.get(event.workflow_id)
            if existing and existing.target_node_id is None:
                node_id = getattr(event.target, "node_id", None)
                provider_id = getattr(event.target, "provider_id", None)
                self._active_work[event.workflow_id] = existing.model_copy(
                    update={
                        "target_node_id": node_id,
                        "target_provider_id": provider_id,
                    }
                )

    # ------------------------------------------------------------------
    # Ecosystem event handlers
    # ------------------------------------------------------------------

    async def on_node_discovered(self, event: EcosystemNodeDiscoveredEvent) -> None:
        activity = RecentActivityEntry(
            kind=ActivityKind.NODE_DISCOVERED,
            description=f"Node '{event.node.node_name}' discovered.",
            occurred_at=event.timestamp,
            related_node_id=event.node.node_id,
        )
        async with self._lock:
            self._activity.appendleft(activity)
            self._version += 1

    async def on_node_updated(self, event: EcosystemNodeUpdatedEvent) -> None:
        activity = RecentActivityEntry(
            kind=ActivityKind.NODE_UPDATED,
            description=f"Node '{event.node.node_name}' updated.",
            occurred_at=event.timestamp,
            related_node_id=event.node.node_id,
        )
        async with self._lock:
            self._activity.appendleft(activity)
            self._version += 1

    async def on_node_stale(self, event: EcosystemNodeStaleEvent) -> None:
        activity = RecentActivityEntry(
            kind=ActivityKind.NODE_STALE,
            description=f"Node '{event.node_name}' went stale.",
            occurred_at=event.timestamp,
            related_node_id=event.node_id,
        )
        async with self._lock:
            self._activity.appendleft(activity)
            self._version += 1

    async def on_node_lost(self, event: EcosystemNodeLostEvent) -> None:
        activity = RecentActivityEntry(
            kind=ActivityKind.NODE_LOST,
            description=f"Node '{event.node_name}' lost.",
            occurred_at=event.timestamp,
            related_node_id=event.node_id,
        )
        async with self._lock:
            self._activity.appendleft(activity)
            self._version += 1

    # ------------------------------------------------------------------
    # Read API — returns immutable snapshots
    # ------------------------------------------------------------------

    async def get_state(self) -> EcosystemState:
        """Return a frozen snapshot of the current ecosystem state."""
        async with self._lock:
            discovery = self._discovery or EcosystemSnapshot(
                local_node_id="unknown",
                nodes={},
            )
            return EcosystemState(
                version=self._version,
                discovery=discovery,
                active_work=tuple(self._active_work.values()),
                recent_activity=tuple(self._activity),
            )

    async def get_context(self) -> EcosystemContext:
        """Return a frozen ecosystem context with situational metadata."""
        state = await self.get_state()
        from shyam.discovery.ecosystem_models import EcosystemNodeState

        stale_ids = tuple(
            n.node_id
            for n in state.discovery.nodes.values()
            if n.state == EcosystemNodeState.STALE
        )
        return EcosystemContext(
            state=state,
            local_node_id=state.discovery.local_node_id,
            has_active_work=state.running_work_count > 0,
            stale_node_ids=stale_ids,
        )
