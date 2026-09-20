"""Workflow lifecycle domain events - S10.

All events inherit from shyam.events.bus.Event and are published to
the central Shyam EventBus during workflow execution.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from shyam.events.bus import Event
from shyam.navigation.models import NavigationCandidate
from shyam.workflow.state import StepState, WorkflowState


class WorkflowEvent(Event):
    """Base class for all workflow-related domain events."""

    workflow_id: str = Field(description="Unique ID of the workflow.")
    workflow_name: str = Field(description="Name of the workflow.")


class WorkflowStartedEvent(WorkflowEvent):
    """Fired when a workflow begins execution."""

    step_count: int = Field(description="Total number of steps in the workflow.")


class WorkflowCompletedEvent(WorkflowEvent):
    """Fired when a workflow completes all steps successfully."""

    completed_steps_count: int = Field(description="Number of successfully completed steps.")


class WorkflowFailedEvent(WorkflowEvent):
    """Fired when a workflow execution encounters a fatal step error."""

    failed_step_id: str = Field(description="ID of the step that triggered the failure.")
    error: str = Field(description="Error message detailing the failure.")


class WorkflowCancelledEvent(WorkflowEvent):
    """Fired when a workflow is cancelled before or during execution."""

    reason: str = Field(default="Cancelled by user or runtime", description="Cancellation reason.")


class WorkflowStepStartedEvent(WorkflowEvent):
    """Fired when an individual step begins execution."""

    step_id: str = Field(description="ID of the step.")
    capability: str = Field(description="Capability required by the step.")
    target: NavigationCandidate | None = Field(
        default=None,
        description="Target candidate selected by S9 Navigator, if resolved.",
    )


class WorkflowStepCompletedEvent(WorkflowEvent):
    """Fired when an individual step completes successfully."""

    step_id: str = Field(description="ID of the step.")
    capability: str = Field(description="Capability executed.")
    target: NavigationCandidate = Field(description="Target candidate invoked.")
    output: Any | None = Field(default=None, description="Output returned by provider.")


class WorkflowStepFailedEvent(WorkflowEvent):
    """Fired when an individual step fails."""

    step_id: str = Field(description="ID of the step.")
    capability: str = Field(description="Capability that failed.")
    error: str = Field(description="Error diagnostic message.")


class WorkflowStepSkippedEvent(WorkflowEvent):
    """Fired when a step is skipped due to a prior failure or cancellation."""

    step_id: str = Field(description="ID of the step.")
    capability: str = Field(description="Capability of the skipped step.")
    reason: str = Field(description="Reason the step was skipped.")
