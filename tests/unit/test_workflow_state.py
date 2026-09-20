"""Unit tests for Workflow and Step state machines."""

import pytest

from shyam.workflow.state import (
    InvalidStepStateTransitionError,
    InvalidWorkflowStateTransitionError,
    StepState,
    WorkflowState,
    validate_step_transition,
    validate_workflow_transition,
)


def test_workflow_valid_transitions():
    """Verify legal workflow state transitions."""
    validate_workflow_transition(WorkflowState.PENDING, WorkflowState.RUNNING)
    validate_workflow_transition(WorkflowState.PENDING, WorkflowState.CANCELLED)
    validate_workflow_transition(WorkflowState.RUNNING, WorkflowState.COMPLETED)
    validate_workflow_transition(WorkflowState.RUNNING, WorkflowState.FAILED)
    validate_workflow_transition(WorkflowState.RUNNING, WorkflowState.CANCELLED)


def test_workflow_invalid_transitions():
    """Verify illegal workflow state transitions raise InvalidWorkflowStateTransitionError."""
    # Cannot go backward or skip valid flow
    with pytest.raises(InvalidWorkflowStateTransitionError):
        validate_workflow_transition(WorkflowState.PENDING, WorkflowState.COMPLETED)

    with pytest.raises(InvalidWorkflowStateTransitionError):
        validate_workflow_transition(WorkflowState.COMPLETED, WorkflowState.RUNNING)

    with pytest.raises(InvalidWorkflowStateTransitionError):
        validate_workflow_transition(WorkflowState.FAILED, WorkflowState.RUNNING)

    with pytest.raises(InvalidWorkflowStateTransitionError):
        validate_workflow_transition(WorkflowState.CANCELLED, WorkflowState.COMPLETED)


def test_step_valid_transitions():
    """Verify legal step state transitions."""
    validate_step_transition(StepState.PENDING, StepState.RUNNING)
    validate_step_transition(StepState.PENDING, StepState.SKIPPED)
    validate_step_transition(StepState.PENDING, StepState.CANCELLED)
    validate_step_transition(StepState.RUNNING, StepState.COMPLETED)
    validate_step_transition(StepState.RUNNING, StepState.FAILED)
    validate_step_transition(StepState.RUNNING, StepState.CANCELLED)


def test_step_invalid_transitions():
    """Verify illegal step state transitions raise InvalidStepStateTransitionError."""
    with pytest.raises(InvalidStepStateTransitionError):
        validate_step_transition(StepState.PENDING, StepState.COMPLETED)

    with pytest.raises(InvalidStepStateTransitionError):
        validate_step_transition(StepState.COMPLETED, StepState.RUNNING)

    with pytest.raises(InvalidStepStateTransitionError):
        validate_step_transition(StepState.FAILED, StepState.RUNNING)

    with pytest.raises(InvalidStepStateTransitionError):
        validate_step_transition(StepState.SKIPPED, StepState.RUNNING)
