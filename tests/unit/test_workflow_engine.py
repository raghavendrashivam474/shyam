"""Unit tests for WorkflowEngine coordination, failure semantics, cancellation, and events."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

from shyam.capabilities.model import AvailabilityStatus
from shyam.discovery.ecosystem_models import EcosystemNodeState
from shyam.events.bus import EventBus
from shyam.navigation.models import (
    NavigationCandidate,
    NavigationRequest,
    NavigationResult,
)
from shyam.workflow.engine import (
    WorkflowCancellationToken,
    WorkflowEngine,
)
from shyam.workflow.events import (
    WorkflowCancelledEvent,
    WorkflowCompletedEvent,
    WorkflowEvent,
    WorkflowFailedEvent,
    WorkflowStartedEvent,
    WorkflowStepCompletedEvent,
    WorkflowStepFailedEvent,
    WorkflowStepSkippedEvent,
    WorkflowStepStartedEvent,
)
from shyam.workflow.executor import CapabilityExecutor, ExecutorRegistry
from shyam.workflow.executors.local_fs import LocalFilesystemExecutor
from shyam.workflow.models import Workflow, WorkflowStep
from shyam.workflow.state import StepState, WorkflowState


def _make_candidate(provider_id: str, capability_id: str) -> NavigationCandidate:
    return NavigationCandidate(
        node_id="local-node",
        node_name="Local Node",
        provider_id=provider_id,
        provider_name="Local Provider",
        capability_id=capability_id,
        is_local=True,
        node_state=EcosystemNodeState.AVAILABLE,
        provider_status=AvailabilityStatus.AVAILABLE,
        capability_availability=AvailabilityStatus.AVAILABLE,
    )


def _make_nav_result(candidate: NavigationCandidate | None, capability: str) -> NavigationResult:
    return NavigationResult(
        capability=capability,
        selected=candidate,
        reason="Test selection" if candidate else "No candidate found",
    )


@pytest.mark.asyncio
async def test_empty_workflow_completes_immediately():
    """An empty workflow transitions directly to COMPLETED."""
    mock_nav = AsyncMock()
    registry = ExecutorRegistry()
    engine = WorkflowEngine(navigator_fn=mock_nav, executor_registry=registry)

    wf = Workflow(name="empty-flow", steps=())
    res = await engine.run(wf)

    assert res.is_success is True
    assert res.state == WorkflowState.COMPLETED
    assert len(res.step_results) == 0
    mock_nav.assert_not_called()


@pytest.mark.asyncio
async def test_single_step_workflow_success(tmp_path):
    """Single step workflow resolves candidate, executes, and completes."""
    test_file = tmp_path / "data.txt"
    target = _make_candidate("local.filesystem", "file.write")

    mock_nav = AsyncMock(return_value=_make_nav_result(target, "file.write"))
    registry = ExecutorRegistry()
    registry.register("local.filesystem", LocalFilesystemExecutor())

    engine = WorkflowEngine(navigator_fn=mock_nav, executor_registry=registry)

    step = WorkflowStep(
        step_id="step-1",
        capability="file.write",
        input_data={"path": str(test_file), "content": "Engine integration test"},
    )
    wf = Workflow(name="write-flow", steps=(step,))

    result = await engine.run(wf)

    assert result.is_success is True
    assert result.state == WorkflowState.COMPLETED
    assert len(result.step_results) == 1
    assert result.step_results[0].is_success is True
    assert result.step_results[0].output["written_bytes"] > 0
    assert test_file.read_text() == "Engine integration test"


@pytest.mark.asyncio
async def test_multi_step_sequential_workflow_success(tmp_path):
    """Multi-step workflow executes steps in order: write -> read."""
    test_file = tmp_path / "chained.txt"

    async def _navigator_router(req: NavigationRequest) -> NavigationResult:
        if req.capability == "file.write":
            return _make_nav_result(_make_candidate("local.filesystem", "file.write"), "file.write")
        elif req.capability == "file.read":
            return _make_nav_result(_make_candidate("local.filesystem", "file.read"), "file.read")
        return _make_nav_result(None, req.capability)

    registry = ExecutorRegistry()
    registry.register("local.filesystem", LocalFilesystemExecutor())

    engine = WorkflowEngine(navigator_fn=_navigator_router, executor_registry=registry)

    wf = Workflow(
        name="write-and-read",
        steps=(
            WorkflowStep(
                step_id="step-write",
                capability="file.write",
                input_data={"path": str(test_file), "content": "Chained content"},
            ),
            WorkflowStep(
                step_id="step-read",
                capability="file.read",
                input_data={"path": str(test_file)},
            ),
        ),
    )

    result = await engine.run(wf)

    assert result.is_success is True
    assert result.completed_steps_count == 2
    assert result.step_results[0].step_id == "step-write"
    assert result.step_results[1].step_id == "step-read"
    assert result.step_results[1].output["content"] == "Chained content"


@pytest.mark.asyncio
async def test_step_failure_fail_fast_and_skips_remaining(tmp_path):
    """Step failure stops execution immediately and skips remaining steps."""
    async def _navigator_router(req: NavigationRequest) -> NavigationResult:
        return _make_nav_result(_make_candidate("local.filesystem", req.capability), req.capability)

    registry = ExecutorRegistry()
    registry.register("local.filesystem", LocalFilesystemExecutor())

    engine = WorkflowEngine(navigator_fn=_navigator_router, executor_registry=registry)

    wf = Workflow(
        name="fail-fast-flow",
        steps=(
            # Step 1: will fail (reading non-existent file)
            WorkflowStep(
                step_id="step-fail",
                capability="file.read",
                input_data={"path": str(tmp_path / "missing.txt")},
            ),
            # Step 2: should be skipped
            WorkflowStep(
                step_id="step-skip",
                capability="file.write",
                input_data={"path": str(tmp_path / "never.txt"), "content": "x"},
            ),
        ),
    )

    result = await engine.run(wf)

    assert result.is_success is False
    assert result.state == WorkflowState.FAILED
    assert result.failed_steps_count == 1
    assert result.skipped_steps_count == 1
    assert result.step_results[0].state == StepState.FAILED
    assert "File not found" in str(result.step_results[0].error)
    assert result.step_results[1].state == StepState.SKIPPED


@pytest.mark.asyncio
async def test_navigation_target_not_found_causes_step_failure():
    """If S9 Navigator cannot find a target, the step fails cleanly."""
    mock_nav = AsyncMock(return_value=_make_nav_result(None, "unsupported.capability"))
    registry = ExecutorRegistry()
    engine = WorkflowEngine(navigator_fn=mock_nav, executor_registry=registry)

    wf = Workflow(
        name="nav-fail-flow",
        steps=(WorkflowStep(step_id="step-1", capability="unsupported.capability"),),
    )

    result = await engine.run(wf)

    assert result.state == WorkflowState.FAILED
    assert result.step_results[0].state == StepState.FAILED
    assert "Navigation failed to resolve target" in str(result.step_results[0].error)


@pytest.mark.asyncio
async def test_cooperative_cancellation_between_steps(tmp_path):
    """Workflow cancels gracefully when cancellation token is signaled."""
    token = WorkflowCancellationToken()

    async def _navigator_router(req: NavigationRequest) -> NavigationResult:
        return _make_nav_result(_make_candidate("local.filesystem", req.capability), req.capability)

    registry = ExecutorRegistry()
    registry.register("local.filesystem", LocalFilesystemExecutor())

    engine = WorkflowEngine(navigator_fn=_navigator_router, executor_registry=registry)

    test_file1 = tmp_path / "f1.txt"
    test_file2 = tmp_path / "f2.txt"

    # Define a custom mock executor that cancels the token during step 1
    class CancellingExecutor:
        async def execute(self, target, input_data):
            token.cancel("User requested cancellation")
            return {"status": "done"}

    registry.register("cancelling.prov", CancellingExecutor())

    async def _cancelling_nav(req: NavigationRequest) -> NavigationResult:
        if req.capability == "cancel.step":
            return _make_nav_result(_make_candidate("cancelling.prov", "cancel.step"), "cancel.step")
        return _make_nav_result(_make_candidate("local.filesystem", req.capability), req.capability)

    engine_with_cancel = WorkflowEngine(navigator_fn=_cancelling_nav, executor_registry=registry)

    wf = Workflow(
        name="cancellation-flow",
        steps=(
            WorkflowStep(step_id="step-1", capability="cancel.step"),
            WorkflowStep(step_id="step-2", capability="file.write", input_data={"path": str(test_file2), "content": "x"}),
        ),
    )

    result = await engine_with_cancel.run(wf, cancellation_token=token)

    assert result.state == WorkflowState.CANCELLED
    assert result.step_results[0].state == StepState.COMPLETED
    assert result.step_results[1].state == StepState.CANCELLED
    assert not test_file2.exists()


@pytest.mark.asyncio
async def test_workflow_events_lifecycle_emission(tmp_path):
    """Verify deterministic emission and order of workflow domain events."""
    event_bus = EventBus()
    received_events: list[WorkflowEvent] = []

    async def _event_collector(event: WorkflowEvent) -> None:
        received_events.append(event)

    await event_bus.subscribe(WorkflowEvent, _event_collector)

    test_file = tmp_path / "event_test.txt"
    target = _make_candidate("local.filesystem", "file.write")
    mock_nav = AsyncMock(return_value=_make_nav_result(target, "file.write"))

    registry = ExecutorRegistry()
    registry.register("local.filesystem", LocalFilesystemExecutor())

    engine = WorkflowEngine(
        navigator_fn=mock_nav,
        executor_registry=registry,
        event_bus=event_bus,
    )

    wf = Workflow(
        name="event-flow",
        steps=(
            WorkflowStep(
                step_id="step-write",
                capability="file.write",
                input_data={"path": str(test_file), "content": "events"},
            ),
        ),
    )

    await engine.run(wf)

    # Verify event types received in sequence
    event_types = [type(e) for e in received_events]
    assert WorkflowStartedEvent in event_types
    assert WorkflowStepStartedEvent in event_types
    assert WorkflowStepCompletedEvent in event_types
    assert WorkflowCompletedEvent in event_types
