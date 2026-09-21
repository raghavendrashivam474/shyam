"""Composite capability engine - S11.

Resolves bindings, constructs S10 Workflows, and executes them through
the existing WorkflowEngine. This is the primary orchestration layer
that makes capabilities composable and reusable.

Architecture:
    CompositeEngine
        -> resolves bindings
        -> builds single-step S10 Workflow per composite step
        -> calls WorkflowEngine.run()
        -> accumulates step outputs
        -> resolves output bindings
        -> returns CompositeResult

S10 is never bypassed. S9 navigation happens inside S10 as usual.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from shyam.composite.errors import (
    CompositeBindingError,
    CompositeInputError,
    CompositeNotFoundError,
)
from shyam.composite.models import (
    Binding,
    BindingSource,
    CompositeCapability,
    CompositeResult,
    CompositeStep,
)
from shyam.composite.registry import CompositeCapabilityRegistry
from shyam.workflow.engine import WorkflowCancellationToken, WorkflowEngine
from shyam.workflow.models import Workflow, WorkflowStep

logger = logging.getLogger("shyam.composite.engine")


@dataclass
class _ExecutionContext:
    """Internal mutable state accumulated during composite execution."""

    composite_inputs: dict[str, Any]
    step_outputs: dict[str, Any] = field(default_factory=dict)


class CompositeEngine:
    """Executes composite capabilities by orchestrating the S10 WorkflowEngine.

    Each composite step is executed as an individual single-step Workflow
    through the existing engine, preserving all S10 semantics (navigation,
    executor dispatch, events, cancellation, fail-fast).
    """

    def __init__(
        self,
        workflow_engine: WorkflowEngine,
        registry: CompositeCapabilityRegistry,
    ) -> None:
        self._engine = workflow_engine
        self._registry = registry

    async def invoke(
        self,
        capability_id: str,
        inputs: dict[str, Any],
        cancellation_token: WorkflowCancellationToken | None = None,
    ) -> CompositeResult:
        """Invoke a registered composite capability.

        Args:
            capability_id: The namespaced ID of the composite to invoke.
            inputs: Input values matching the composite's input contract.
            cancellation_token: Optional S10 cancellation token.

        Returns:
            CompositeResult with resolved outputs and step results.

        Raises:
            CompositeNotFoundError: If the capability is not registered.
            CompositeInputError: If inputs violate the contract.
            CompositeBindingError: If a binding cannot be resolved at runtime.
        """
        composite = self._registry.require(capability_id)

        # 1. Validate inputs against the composite's input contract
        self._validate_inputs(composite, inputs)

        # 2. Initialize execution context
        context = _ExecutionContext(composite_inputs=dict(inputs))
        all_step_results: list[Any] = []

        logger.info(
            "Invoking composite '%s' with %d step(s)",
            capability_id,
            len(composite.steps),
        )

        # 3. Execute each step sequentially through S10
        for step in composite.steps:
            # Check cancellation before starting next step
            if cancellation_token and cancellation_token.is_cancelled:
                logger.info(
                    "Composite '%s' cancelled before step '%s'",
                    capability_id,
                    step.step_id,
                )
                return CompositeResult(
                    capability_id=capability_id,
                    state="CANCELLED",
                    outputs={},
                    step_results=tuple(all_step_results),
                    error_detail=cancellation_token.reason,
                )

            # Resolve this step's input bindings
            resolved_input = self._resolve_step_bindings(step, context)

            # Build a single-step S10 Workflow
            wf_step = WorkflowStep(
                step_id=step.step_id,
                capability=step.capability,
                constraints=step.constraints,
                input_data=resolved_input,
                description=step.description,
            )
            workflow = Workflow(
                name=f"{capability_id}::{step.step_id}",
                steps=(wf_step,),
                metadata={"composite_id": capability_id},
            )

            # Execute through S10 WorkflowEngine
            wf_result = await self._engine.run(workflow, cancellation_token)
            step_result = wf_result.step_results[0]
            all_step_results.append(step_result)

            # Fail-fast: if this step failed, stop and return
            if not step_result.is_success:
                logger.warning(
                    "Composite '%s' failed at step '%s': %s",
                    capability_id,
                    step.step_id,
                    step_result.error,
                )
                return CompositeResult(
                    capability_id=capability_id,
                    state=wf_result.state.value,
                    outputs={},
                    step_results=tuple(all_step_results),
                    error_detail=wf_result.error_detail
                    or f"Step '{step.step_id}' failed",
                )

            # Accumulate output for downstream step bindings
            context.step_outputs[step.step_id] = step_result.output
            logger.debug(
                "Composite '%s' step '%s' completed",
                capability_id,
                step.step_id,
            )

        # 4. Resolve output bindings
        resolved_outputs = self._resolve_output_bindings(composite, context)

        logger.info("Composite '%s' completed successfully", capability_id)

        return CompositeResult(
            capability_id=capability_id,
            state="COMPLETED",
            outputs=resolved_outputs,
            step_results=tuple(all_step_results),
        )

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_inputs(
        composite: CompositeCapability,
        inputs: dict[str, Any],
    ) -> None:
        """Verify that all declared inputs are provided."""
        missing = [name for name in composite.inputs if name not in inputs]
        if missing:
            raise CompositeInputError(
                composite.capability_id,
                f"Missing required input(s): {', '.join(missing)}",
            )

    # ------------------------------------------------------------------
    # Binding resolution
    # ------------------------------------------------------------------

    def _resolve_step_bindings(
        self,
        step: CompositeStep,
        context: _ExecutionContext,
    ) -> dict[str, Any]:
        """Resolve all input bindings for a step into concrete values."""
        resolved: dict[str, Any] = {}
        for field_name, binding in step.input_bindings.items():
            resolved[field_name] = self._resolve_binding_value(
                binding, step.step_id, field_name, context
            )
        return resolved

    def _resolve_output_bindings(
        self,
        composite: CompositeCapability,
        context: _ExecutionContext,
    ) -> dict[str, Any]:
        """Resolve all output bindings into the final composite result."""
        resolved: dict[str, Any] = {}
        for out_name, binding in composite.outputs.items():
            resolved[out_name] = self._resolve_binding_value(
                binding, "output", out_name, context
            )
        return resolved

    @staticmethod
    def _resolve_binding_value(
        binding: Binding,
        step_id: str,
        field_name: str,
        context: _ExecutionContext,
    ) -> Any:
        """Resolve a single binding to its concrete value.

        Supports optional key extraction from dict-valued sources.
        No expressions, no transformations — deterministic lookup only.
        """
        # 1. Locate the source value
        if binding.source == BindingSource.INPUT:
            if binding.source_id not in context.composite_inputs:
                raise CompositeBindingError(
                    step_id,
                    field_name,
                    f"Input '{binding.source_id}' not found in execution context",
                )
            value = context.composite_inputs[binding.source_id]

        elif binding.source == BindingSource.STEP:
            if binding.source_id not in context.step_outputs:
                raise CompositeBindingError(
                    step_id,
                    field_name,
                    f"Step output '{binding.source_id}' not available "
                    f"(step may not have executed yet)",
                )
            value = context.step_outputs[binding.source_id]

        else:
            raise CompositeBindingError(
                step_id,
                field_name,
                f"Unknown binding source type: {binding.source}",
            )

        # 2. Optional key extraction
        if binding.source_key is not None:
            if not isinstance(value, dict):
                raise CompositeBindingError(
                    step_id,
                    field_name,
                    f"Cannot extract key '{binding.source_key}' from "
                    f"non-dict value of type {type(value).__name__}",
                )
            if binding.source_key not in value:
                raise CompositeBindingError(
                    step_id,
                    field_name,
                    f"Key '{binding.source_key}' not found in source dict",
                )
            value = value[binding.source_key]

        return value
