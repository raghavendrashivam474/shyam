"""Edge case and regression unit tests for the Workflow subsystem."""

from unittest.mock import AsyncMock
import pytest

from shyam.capabilities.model import AvailabilityStatus
from shyam.discovery.ecosystem_models import EcosystemNodeState
from shyam.navigation.models import (
    NavigationCandidate,
    NavigationRequest,
    NavigationResult,
)
from shyam.workflow.engine import WorkflowCancellationToken, WorkflowEngine
from shyam.workflow.executor import ExecutorRegistry
from shyam.workflow.executors.local_fs import LocalFilesystemExecutor
from shyam.workflow.models import Workflow, WorkflowStep
from shyam.workflow.state import StepState, WorkflowState


def _candidate(provider_id: str, capability_id: str) -> NavigationCandidate:
    return NavigationCandidate(
        node_id="test-node",
        node_name="Test Node",
        provider_id=provider_id,
        provider_name="Test Provider",
        capability_id=capability_id,
        is_local=True,
        node_state=EcosystemNodeState.AVAILABLE,
        provider_status=AvailabilityStatus.AVAILABLE,
        capability_availability=AvailabilityStatus.AVAILABLE,
    )


@pytest.mark.asyncio
async def test_workflow_cancelled_before_start():
    """Workflow initialized with an already cancelled token transitions to CANCELLED without invoking steps."""
    token = WorkflowCancellationToken()
    token.cancel("Cancelled before start")

    mock_nav = AsyncMock()
    registry = ExecutorRegistry()
    engine = WorkflowEngine(navigator_fn=mock_nav, executor_registry=registry)

    wf = Workflow(
        name="pre-cancelled",
        steps=(WorkflowStep(step_id="s1", capability="file.read"),),
    )

    result = await engine.run(wf, cancellation_token=token)

    assert result.state == WorkflowState.CANCELLED
    assert result.error_detail == "Cancelled before start"
    assert len(result.step_results) == 1
    assert result.step_results[0].state == StepState.CANCELLED
    mock_nav.assert_not_called()


@pytest.mark.asyncio
async def test_workflow_mixed_provider_steps(tmp_path):
    """Workflow coordinating multiple different provider executors in sequence."""
    test_file = tmp_path / "mixed.txt"

    # Executor for a custom mock provider
    class AnalyticsExecutor:
        async def execute(self, target, input_data):
            return {"processed_chars": len(input_data.get("text", ""))}

    registry = ExecutorRegistry()
    registry.register("local.filesystem", LocalFilesystemExecutor())
    registry.register("analytics.provider", AnalyticsExecutor())

    async def _nav_router(req: NavigationRequest) -> NavigationResult:
        if req.capability == "file.write":
            return NavigationResult(
                capability="file.write",
                selected=_candidate("local.filesystem", "file.write"),
            )
        elif req.capability == "analytics.compute":
            return NavigationResult(
                capability="analytics.compute",
                selected=_candidate("analytics.provider", "analytics.compute"),
            )
        return NavigationResult(capability=req.capability, selected=None)

    engine = WorkflowEngine(navigator_fn=_nav_router, executor_registry=registry)

    wf = Workflow(
        name="mixed-flow",
        steps=(
            WorkflowStep(
                step_id="step-write",
                capability="file.write",
                input_data={"path": str(test_file), "content": "Sample Analytics Payload"},
            ),
            WorkflowStep(
                step_id="step-compute",
                capability="analytics.compute",
                input_data={"text": "Sample Analytics Payload"},
            ),
        ),
    )

    result = await engine.run(wf)

    assert result.is_success is True
    assert result.completed_steps_count == 2
    assert result.step_results[0].target.provider_id == "local.filesystem"
    assert result.step_results[1].target.provider_id == "analytics.provider"
    assert result.step_results[1].output["processed_chars"] == 24


@pytest.mark.asyncio
async def test_workflow_step_with_custom_constraints():
    """Workflow step constraints are forwarded transparently to S9 Navigator."""
    captured_request: list[NavigationRequest] = []

    async def _mock_nav(req: NavigationRequest) -> NavigationResult:
        captured_request.append(req)
        return NavigationResult(
            capability=req.capability,
            selected=_candidate("local.filesystem", req.capability),
        )

    registry = ExecutorRegistry()
    registry.register("local.filesystem", LocalFilesystemExecutor())
    engine = WorkflowEngine(navigator_fn=_mock_nav, executor_registry=registry)

    wf = Workflow(
        name="constrained-step",
        steps=(
            WorkflowStep(
                step_id="s1",
                capability="file.list",
                input_data={"path": "."},
            ),
        ),
    )

    res = await engine.run(wf)
    assert res.is_success is True
    assert len(captured_request) == 1
    assert captured_request[0].capability == "file.list"
