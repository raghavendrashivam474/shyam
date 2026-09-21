"""Ecosystem State and Context domain models - S12.

Provides frozen, immutable representations of the current ecosystem state
(nodes, active work, recent activity) and the surrounding context that
helps Shyam understand what is happening right now.

Consumes S8 discovery snapshots and S10 workflow events. Does not replace
or duplicate either subsystem.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from shyam.discovery.ecosystem_models import EcosystemSnapshot


class WorkStatus(StrEnum):
    """Lifecycle status of a tracked work item."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActiveWorkItem(BaseModel):
    """Represents a single workflow currently executing or recently finished."""

    model_config = ConfigDict(frozen=True)

    workflow_id: str = Field(description="Unique workflow identifier.")
    workflow_name: str = Field(description="Human-readable workflow name.")
    status: WorkStatus = Field(
        default=WorkStatus.RUNNING,
        description="Current lifecycle status.",
    )
    step_count: int = Field(
        default=0,
        description="Total steps in the workflow.",
    )
    completed_steps: int = Field(
        default=0,
        description="Number of steps completed so far.",
    )
    target_node_id: str | None = Field(
        default=None,
        description="Node ID of the primary execution target, if known.",
    )
    target_provider_id: str | None = Field(
        default=None,
        description="Provider ID of the primary execution target, if known.",
    )
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the workflow started.",
    )
    finished_at: datetime | None = Field(
        default=None,
        description="When the workflow reached a terminal state.",
    )
    error: str | None = Field(
        default=None,
        description="Error message if the workflow failed.",
    )


class ActivityKind(StrEnum):
    """Category of a recent ecosystem activity entry."""

    NODE_DISCOVERED = "node_discovered"
    NODE_UPDATED = "node_updated"
    NODE_STALE = "node_stale"
    NODE_LOST = "node_lost"
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_CANCELLED = "workflow_cancelled"


class RecentActivityEntry(BaseModel):
    """A single entry in the recent ecosystem activity feed."""

    model_config = ConfigDict(frozen=True)

    kind: ActivityKind = Field(description="Category of activity.")
    description: str = Field(description="Human-readable summary.")
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this activity occurred.",
    )
    related_node_id: str | None = Field(
        default=None,
        description="Associated node, if any.",
    )
    related_workflow_id: str | None = Field(
        default=None,
        description="Associated workflow, if any.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context-specific data.",
    )


class EcosystemState(BaseModel):
    """Immutable point-in-time snapshot of the full ecosystem state.

    Combines S8 discovery facts with S12 active-work and activity tracking.
    """

    model_config = ConfigDict(frozen=True)

    version: int = Field(
        description="Monotonic local state revision number.",
    )
    captured_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this state snapshot was captured.",
    )
    discovery: EcosystemSnapshot = Field(
        description="The underlying S8 ecosystem discovery snapshot.",
    )
    active_work: tuple[ActiveWorkItem, ...] = Field(
        default_factory=tuple,
        description="Workflows currently in RUNNING status.",
    )
    recent_activity: tuple[RecentActivityEntry, ...] = Field(
        default_factory=tuple,
        description="Most recent ecosystem activity entries (newest first).",
    )

    @property
    def total_nodes(self) -> int:
        return self.discovery.total_nodes

    @property
    def active_node_count(self) -> int:
        return len(self.discovery.active_nodes)

    @property
    def running_work_count(self) -> int:
        return len(self.active_work)


class EcosystemContext(BaseModel):
    """Higher-level context wrapper around EcosystemState.

    Provides the situational awareness Shyam needs for orchestration
    decisions. Currently wraps state directly; future sprints may add
    trust, peer, and continuity metadata here.
    """

    model_config = ConfigDict(frozen=True)

    state: EcosystemState = Field(
        description="The current ecosystem state snapshot.",
    )
    local_node_id: str = Field(
        description="Identity of the local Shyam node.",
    )
    has_active_work: bool = Field(
        default=False,
        description="Whether any workflows are currently running.",
    )
    stale_node_ids: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Node IDs currently marked as stale.",
    )
