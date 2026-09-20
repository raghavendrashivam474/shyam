"""Workflow and Step lifecycle states and transition logic.

Follows the strict transition validation pattern defined in shyam.core.lifecycle.
"""

from __future__ import annotations

from enum import StrEnum


class WorkflowState(StrEnum):
    """Lifecycle states for a Workflow execution."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepState(StrEnum):
    """Lifecycle states for an individual WorkflowStep."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


# Strict allowable transitions map for Workflow
VALID_WORKFLOW_TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
    WorkflowState.PENDING: {
        WorkflowState.RUNNING,
        WorkflowState.CANCELLED,
    },
    WorkflowState.RUNNING: {
        WorkflowState.COMPLETED,
        WorkflowState.FAILED,
        WorkflowState.CANCELLED,
    },
    WorkflowState.COMPLETED: set(),  # Terminal state
    WorkflowState.FAILED: set(),     # Terminal state
    WorkflowState.CANCELLED: set(),  # Terminal state
}

# Strict allowable transitions map for Step
VALID_STEP_TRANSITIONS: dict[StepState, set[StepState]] = {
    StepState.PENDING: {
        StepState.RUNNING,
        StepState.SKIPPED,
        StepState.CANCELLED,
    },
    StepState.RUNNING: {
        StepState.COMPLETED,
        StepState.FAILED,
        StepState.CANCELLED,
    },
    StepState.COMPLETED: set(),  # Terminal state
    StepState.FAILED: set(),     # Terminal state
    StepState.SKIPPED: set(),    # Terminal state
    StepState.CANCELLED: set(),  # Terminal state
}


class InvalidWorkflowStateTransitionError(RuntimeError):
    """Raised when an illegal workflow state transition is attempted."""

    def __init__(self, current_state: WorkflowState, target_state: WorkflowState) -> None:
        super().__init__(
            f"Illegal workflow state transition attempted: "
            f"{current_state.value} -> {target_state.value}"
        )
        self.current_state = current_state
        self.target_state = target_state


class InvalidStepStateTransitionError(RuntimeError):
    """Raised when an illegal step state transition is attempted."""

    def __init__(self, current_state: StepState, target_state: StepState) -> None:
        super().__init__(
            f"Illegal step state transition attempted: "
            f"{current_state.value} -> {target_state.value}"
        )
        self.current_state = current_state
        self.target_state = target_state


def validate_workflow_transition(current: WorkflowState, target: WorkflowState) -> None:
    """Validate whether transitioning a workflow from current to target is allowed.

    Raises:
        InvalidWorkflowStateTransitionError: If the transition is illegal.
    """
    allowed = VALID_WORKFLOW_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidWorkflowStateTransitionError(current, target)


def validate_step_transition(current: StepState, target: StepState) -> None:
    """Validate whether transitioning a step from current to target is allowed.

    Raises:
        InvalidStepStateTransitionError: If the transition is illegal.
    """
    allowed = VALID_STEP_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStepStateTransitionError(current, target)
