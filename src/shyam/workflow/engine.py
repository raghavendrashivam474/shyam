"""Workflow Engine orchestrator - S10.

Coordinates the sequential execution of workflow steps by querying the S9 Hybrid Navigator
for execution targets and dispatching invocation to the registered CapabilityExecutor.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

from shyam.events.bus import EventBus
from shyam.navigation.models import NavigationRequest, NavigationResult
from shyam.workflow.errors import (
    ExecutorNotFoundError,
    NavigationTargetNotFoundError,
    StepExecutionError,
    WorkflowExecutionError,
)
from shyam.workflow.events import (
    WorkflowCancelledEvent,
    WorkflowCompletedEvent,
    WorkflowFailedEvent,
    WorkflowStartedEvent,
    WorkflowStepCompletedEvent,
    WorkflowStepFailedEvent,
    WorkflowStepSkippedEvent,
    WorkflowStepStartedEvent,
)
from shyam.workflow.executor import ExecutorRegistry
from shyam.workflow.models import (
    StepResult,
    Workflow,
    WorkflowResult,
    WorkflowStep,
)
from shyam.workflow.state import (
    StepState,
    WorkflowState,
    validate_step_transition,
    validate_workflow_transition,
)

logger = logging.getLogger("shyam.workflow.engine")

# Type alias for navigator callable: (NavigationRequest) -> Awaitable[NavigationResult]
NavigatorCallable = Callable[[NavigationRequest], Coroutine[Any, Any, NavigationResult]]


class WorkflowCancellationToken:
    """Cooperative cancellation token for in-flight workflows."""

    def __init__(self) -> None:
        self._cancelled = False
        self._reason = ""

    def cancel(self, reason: str = "Workflow cancelled by request") -> None:
        """Signal cancellation."""
        self._cancelled = True
        self._reason = reason

    @property
    def is_cancelled(self) -> bool:
        """True if cancellation was signaled."""
        return self._cancelled

    @property
    def reason(self) -> str:
        """Cancellation reason."""
        return self._reason


class WorkflowEngine:
    """Sequential Workflow Engine.

    Executes structured workflows step-by-step:
    1. Evaluates S9 Navigation for the step capability.
    2. Resolves target candidate (node, provider, capability).
    3. Invokes provider via CapabilityExecutor adapter.
    4. Handles fail-fast error propagation and cancellation.
    5. Publishes lifecycle events to the EventBus.
    """

    def __init__(
        self,
        navigator_fn: NavigatorCallable,
        executor_registry: ExecutorRegistry,
        event_bus: EventBus | None = None,
    ) -> None:
        """Initialize the WorkflowEngine.

        Args:
            navigator_fn: Async callable resolving a NavigationRequest to NavigationResult.
            executor_registry: Registry containing provider CapabilityExecutors.
            event_bus: Optional EventBus for publishing domain events.
        """
        self._navigator = navigator_fn
        self._executors = executor_registry
        self._events = event_bus

    async def _publish(self, event: Any) -> None:
        """Helper to publish events if EventBus is present."""
        if self._events:
            await self._events.publish(event)

    async def run(
        self,
        workflow: Workflow,
        cancellation_token: WorkflowCancellationToken | None = None,
    ) -> WorkflowResult:
        """Execute a Workflow sequentially.

        Args:
            workflow: The immutable Workflow definition.
            cancellation_token: Optional token for cooperative cancellation.

        Returns:
            WorkflowResult summarizing the outcome of all steps.
        """
        token = cancellation_token or WorkflowCancellationToken()
        wf_id = workflow.workflow_id
        wf_name = workflow.name
        started_at = datetime.now(UTC)

        # Handle empty workflow edge case
        if not workflow.steps:
            logger.info("Workflow '%s' has 0 steps. Marking COMPLETED.", wf_name)
            res = WorkflowResult(
                workflow_id=wf_id,
                name=wf_name,
                state=WorkflowState.COMPLETED,
                step_results=(),
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )
            await self._publish(
                WorkflowStartedEvent(workflow_id=wf_id, workflow_name=wf_name, step_count=0)
            )
            await self._publish(
                WorkflowCompletedEvent(
                    workflow_id=wf_id, workflow_name=wf_name, completed_steps_count=0
                )
            )
            return res

        # Check for pre-execution cancellation
        if token.is_cancelled:
            logger.info("Workflow '%s' cancelled prior to execution.", wf_name)
            step_results = tuple(
                StepResult(
                    step_id=step.step_id,
                    capability=step.capability,
                    state=StepState.CANCELLED,
                    error=token.reason,
                )
                for step in workflow.steps
            )
            await self._publish(
                WorkflowCancelledEvent(
                    workflow_id=wf_id,
                    workflow_name=wf_name,
                    reason=token.reason,
                )
            )
            return WorkflowResult(
                workflow_id=wf_id,
                name=wf_name,
                state=WorkflowState.CANCELLED,
                step_results=step_results,
                error_detail=token.reason,
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )

        # Transition to RUNNING
        validate_workflow_transition(WorkflowState.PENDING, WorkflowState.RUNNING)
        await self._publish(
            WorkflowStartedEvent(
                workflow_id=wf_id,
                workflow_name=wf_name,
                step_count=len(workflow.steps),
            )
        )

        step_results_list: list[StepResult] = []
        workflow_failed = False
        workflow_error: str | None = None
        workflow_cancelled = False

        for index, step in enumerate(workflow.steps):
            # Check cooperative cancellation before executing next step
            if token.is_cancelled:
                logger.info(
                    "Workflow '%s' cancelled before step '%s'.",
                    wf_name,
                    step.step_id,
                )
                workflow_cancelled = True
                workflow_error = token.reason

                # Mark current and remaining steps as CANCELLED or SKIPPED
                for remaining_step in workflow.steps[index:]:
                    step_res = StepResult(
                        step_id=remaining_step.step_id,
                        capability=remaining_step.capability,
                        state=StepState.CANCELLED,
                        error=token.reason,
                    )
                    step_results_list.append(step_res)
                    await self._publish(
                        WorkflowStepSkippedEvent(
                            workflow_id=wf_id,
                            workflow_name=wf_name,
                            step_id=remaining_step.step_id,
                            capability=remaining_step.capability,
                            reason=f"Workflow cancelled: {token.reason}",
                        )
                    )
                break

            # If a prior step failed, skip all subsequent steps (Fail-Fast)
            if workflow_failed:
                step_res = StepResult(
                    step_id=step.step_id,
                    capability=step.capability,
                    state=StepState.SKIPPED,
                    error="Skipped due to earlier step failure",
                )
                step_results_list.append(step_res)
                await self._publish(
                    WorkflowStepSkippedEvent(
                        workflow_id=wf_id,
                        workflow_name=wf_name,
                        step_id=step.step_id,
                        capability=step.capability,
                        reason="Prior step failed",
                    )
                )
                continue

            # Execute the step
            step_result = await self._execute_step(wf_id, wf_name, step)
            step_results_list.append(step_result)

            if not step_result.is_success:
                workflow_failed = True
                workflow_error = step_result.error or f"Step '{step.step_id}' failed"
                await self._publish(
                    WorkflowFailedEvent(
                        workflow_id=wf_id,
                        workflow_name=wf_name,
                        failed_step_id=step.step_id,
                        error=workflow_error,
                    )
                )

        completed_at = datetime.now(UTC)

        # Determine terminal workflow state
        if workflow_cancelled:
            final_state = WorkflowState.CANCELLED
            await self._publish(
                WorkflowCancelledEvent(
                    workflow_id=wf_id,
                    workflow_name=wf_name,
                    reason=token.reason,
                )
            )
        elif workflow_failed:
            final_state = WorkflowState.FAILED
        else:
            final_state = WorkflowState.COMPLETED
            await self._publish(
                WorkflowCompletedEvent(
                    workflow_id=wf_id,
                    workflow_name=wf_name,
                    completed_steps_count=len(workflow.steps),
                )
            )

        return WorkflowResult(
            workflow_id=wf_id,
            name=wf_name,
            state=final_state,
            step_results=tuple(step_results_list),
            error_detail=workflow_error,
            started_at=started_at,
            completed_at=completed_at,
        )

    async def _execute_step(
        self,
        workflow_id: str,
        workflow_name: str,
        step: WorkflowStep,
    ) -> StepResult:
        """Execute a single step through navigation resolution and provider dispatch."""
        step_started_at = datetime.now(UTC)
        step_id = step.step_id
        cap = step.capability

        await self._publish(
            WorkflowStepStartedEvent(
                workflow_id=workflow_id,
                workflow_name=workflow_name,
                step_id=step_id,
                capability=cap,
            )
        )

        # 1. Resolve target candidate via S9 Navigator
        nav_req = NavigationRequest(capability=cap, constraints=step.constraints)
        try:
            nav_result = await self._navigator(nav_req)
        except Exception as exc:
            logger.exception("Navigator invocation failed for step '%s': %s", step_id, exc)
            err_msg = f"Navigator invocation error: {exc}"
            await self._publish(
                WorkflowStepFailedEvent(
                    workflow_id=workflow_id,
                    workflow_name=workflow_name,
                    step_id=step_id,
                    capability=cap,
                    error=err_msg,
                )
            )
            return StepResult(
                step_id=step_id,
                capability=cap,
                state=StepState.FAILED,
                error=err_msg,
                started_at=step_started_at,
                completed_at=datetime.now(UTC),
            )

        if not nav_result.has_selection or nav_result.selected is None:
            reason = nav_result.reason or "No eligible candidate available"
            err_msg = f"Navigation failed to resolve target: {reason}"
            logger.warning("Step '%s' (%s) target resolution failed: %s", step_id, cap, reason)
            await self._publish(
                WorkflowStepFailedEvent(
                    workflow_id=workflow_id,
                    workflow_name=workflow_name,
                    step_id=step_id,
                    capability=cap,
                    error=err_msg,
                )
            )
            return StepResult(
                step_id=step_id,
                capability=cap,
                state=StepState.FAILED,
                error=err_msg,
                started_at=step_started_at,
                completed_at=datetime.now(UTC),
            )

        target = nav_result.selected

        # 2. Lookup provider executor
        try:
            executor = self._executors.get(target.provider_id)
        except ExecutorNotFoundError as exc:
            err_msg = f"No executor available for provider '{target.provider_id}'"
            logger.error("Step '%s': %s", step_id, err_msg)
            await self._publish(
                WorkflowStepFailedEvent(
                    workflow_id=workflow_id,
                    workflow_name=workflow_name,
                    step_id=step_id,
                    capability=cap,
                    error=err_msg,
                )
            )
            return StepResult(
                step_id=step_id,
                capability=cap,
                state=StepState.FAILED,
                target=target,
                error=err_msg,
                started_at=step_started_at,
                completed_at=datetime.now(UTC),
            )

        # 3. Execute capability on provider
        try:
            output = await executor.execute(target=target, input_data=step.input_data)
            step_completed_at = datetime.now(UTC)

            await self._publish(
                WorkflowStepCompletedEvent(
                    workflow_id=workflow_id,
                    workflow_name=workflow_name,
                    step_id=step_id,
                    capability=cap,
                    target=target,
                    output=output,
                )
            )

            return StepResult(
                step_id=step_id,
                capability=cap,
                state=StepState.COMPLETED,
                target=target,
                output=output,
                started_at=step_started_at,
                completed_at=step_completed_at,
            )

        except Exception as exc:
            step_completed_at = datetime.now(UTC)
            err_msg = str(exc)
            logger.warning("Step '%s' execution failed on provider '%s': %s", step_id, target.provider_id, exc)

            await self._publish(
                WorkflowStepFailedEvent(
                    workflow_id=workflow_id,
                    workflow_name=workflow_name,
                    step_id=step_id,
                    capability=cap,
                    error=err_msg,
                )
            )

            return StepResult(
                step_id=step_id,
                capability=cap,
                state=StepState.FAILED,
                target=target,
                error=err_msg,
                started_at=step_started_at,
                completed_at=step_completed_at,
            )
