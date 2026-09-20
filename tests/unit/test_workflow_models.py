"""Unit tests for Workflow domain models."""

import pytest

from shyam.navigation.models import NavigationCandidate, NavigationConstraints
from shyam.workflow.models import (
    StepResult,
    Workflow,
    WorkflowResult,
    WorkflowStep,
)
from shyam.workflow.state import StepState, WorkflowState


def test_workflow_step_validation():
    """Test validation of WorkflowStep fields."""
    step = WorkflowStep(
        step_id="step-1",
        capability="file.read",
        input_data={"path": "/tmp/test.txt"},
        description="Read file",
    )
    assert step.step_id == "step-1"
    assert step.capability == "file.read"
    assert step.input_data == {"path": "/tmp/test.txt"}

    # Invalid empty step_id
    with pytest.raises(ValueError, match="step_id must be a non-empty string"):
        WorkflowStep(step_id="", capability="file.read")

    # Invalid non-namespaced capability
    with pytest.raises(ValueError, match="must be namespaced"):
        WorkflowStep(step_id="step-1", capability="fileread")


def test_workflow_validation_unique_steps():
    """Workflow rejects duplicate step IDs."""
    step1 = WorkflowStep(step_id="step-1", capability="file.read")
    step2 = WorkflowStep(step_id="step-1", capability="file.write")

    with pytest.raises(ValueError, match="Duplicate step_id found"):
        Workflow(
            name="duplicate-workflow",
            steps=(step1, step2),
        )


def test_workflow_creation_and_immutability():
    """Workflow and WorkflowStep are immutable frozen models."""
    step = WorkflowStep(step_id="step-1", capability="file.read")
    wf = Workflow(
        name="test-workflow",
        steps=(step,),
    )
    assert len(wf.steps) == 1
    assert wf.name == "test-workflow"

    with pytest.raises(Exception):
        wf.name = "mutated"  # type: ignore[misc]

    with pytest.raises(Exception):
        step.capability = "file.write"  # type: ignore[misc]


def test_step_result_properties():
    """Test StepResult success check and properties."""
    sr = StepResult(
        step_id="step-1",
        capability="file.read",
        state=StepState.COMPLETED,
        output={"bytes": 100},
    )
    assert sr.is_success is True
    assert sr.error is None

    sr_failed = StepResult(
        step_id="step-2",
        capability="file.write",
        state=StepState.FAILED,
        error="Permission denied",
    )
    assert sr_failed.is_success is False


def test_workflow_result_metrics():
    """Test WorkflowResult summary counts and state properties."""
    s1 = StepResult(step_id="s1", capability="file.read", state=StepState.COMPLETED)
    s2 = StepResult(step_id="s2", capability="file.write", state=StepState.FAILED, error="Disk full")
    s3 = StepResult(step_id="s3", capability="file.list", state=StepState.SKIPPED)

    wf_res = WorkflowResult(
        workflow_id="wf-123",
        name="multi-step",
        state=WorkflowState.FAILED,
        step_results=(s1, s2, s3),
        error_detail="Step s2 failed",
    )

    assert wf_res.is_success is False
    assert wf_res.completed_steps_count == 1
    assert wf_res.failed_steps_count == 1
    assert wf_res.skipped_steps_count == 1
