"""Workflow domain models - S10.

Frozen Pydantic models for defining workflows, steps, and execution results.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shyam.navigation.models import NavigationCandidate, NavigationConstraints
from shyam.workflow.state import StepState, WorkflowState


class WorkflowStep(BaseModel):
    """A discrete unit of work within a workflow.

    Each step targets a namespaced capability and optional navigation constraints.
    Execution targets are not hardcoded here; they are resolved via S9 Hybrid Navigator.
    """

    model_config = ConfigDict(frozen=True)

    step_id: str = Field(
        ...,
        description="Unique identifier for this step within the workflow.",
    )
    capability: str = Field(
        ...,
        description="Required namespaced capability ID (e.g. 'file.read').",
    )
    constraints: NavigationConstraints = Field(
        default_factory=NavigationConstraints,
        description="Optional S9 constraints to narrow candidate selection.",
    )
    input_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured input payload passed to the provider during execution.",
    )
    description: str = Field(
        default="",
        description="Human-readable description of what this step does.",
    )

    @field_validator("step_id")
    @classmethod
    def validate_step_id(cls, v: str) -> str:
        """Step ID must be a non-empty string."""
        if not v or not v.strip():
            raise ValueError("step_id must be a non-empty string")
        return v.strip()

    @field_validator("capability")
    @classmethod
    def validate_capability(cls, v: str) -> str:
        """Capability must be a non-empty namespaced identifier."""
        if not v or "." not in v:
            raise ValueError(
                f"Workflow step capability must be namespaced (e.g. 'file.read'), got: '{v}'"
            )
        return v


class StepResult(BaseModel):
    """Immutable record of the execution outcome of a WorkflowStep."""

    model_config = ConfigDict(frozen=True)

    step_id: str = Field(description="The ID of the step executed.")
    capability: str = Field(description="The capability that was executed.")
    state: StepState = Field(description="Final state of the step.")
    target: NavigationCandidate | None = Field(
        default=None,
        description="The candidate selected by S9 and invoked, if any.",
    )
    output: Any | None = Field(
        default=None,
        description="Structured output returned by the provider on success.",
    )
    error: str | None = Field(
        default=None,
        description="Error message / diagnostic details on failure.",
    )
    started_at: datetime | None = Field(
        default=None,
        description="Timestamp when step execution began.",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Timestamp when step reached a terminal state.",
    )

    @property
    def is_success(self) -> bool:
        """True if the step completed successfully."""
        return self.state == StepState.COMPLETED


class Workflow(BaseModel):
    """An ordered, structured sequence of steps to be coordinated by the Workflow Engine."""

    model_config = ConfigDict(frozen=True)

    workflow_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the workflow instance.",
    )
    name: str = Field(
        ...,
        description="Human-readable name of the workflow.",
    )
    description: str = Field(
        default="",
        description="Optional description of the workflow purpose.",
    )
    steps: tuple[WorkflowStep, ...] = Field(
        default_factory=tuple,
        description="Ordered sequence of workflow steps.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible metadata associated with this workflow.",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Name must be non-empty."""
        if not v or not v.strip():
            raise ValueError("Workflow name cannot be empty")
        return v.strip()

    @field_validator("steps")
    @classmethod
    def validate_unique_steps(cls, steps: tuple[WorkflowStep, ...]) -> tuple[WorkflowStep, ...]:
        """All step IDs in a workflow must be unique."""
        seen_ids: set[str] = set()
        for step in steps:
            if step.step_id in seen_ids:
                raise ValueError(
                    f"Duplicate step_id found in workflow: '{step.step_id}'"
                )
            seen_ids.add(step.step_id)
        return steps


class WorkflowResult(BaseModel):
    """Immutable aggregate outcome of a Workflow execution."""

    model_config = ConfigDict(frozen=True)

    workflow_id: str = Field(description="The ID of the executed workflow.")
    name: str = Field(description="The name of the workflow.")
    state: WorkflowState = Field(description="Final terminal state of the workflow.")
    step_results: tuple[StepResult, ...] = Field(
        default_factory=tuple,
        description="Ordered results for each step in the workflow.",
    )
    error_detail: str | None = Field(
        default=None,
        description="Error description if the workflow failed.",
    )
    started_at: datetime | None = Field(
        default=None,
        description="Timestamp when workflow execution began.",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Timestamp when workflow concluded.",
    )

    @property
    def is_success(self) -> bool:
        """True if the workflow reached COMPLETED state."""
        return self.state == WorkflowState.COMPLETED

    @property
    def completed_steps_count(self) -> int:
        """Count of steps that completed successfully."""
        return sum(1 for s in self.step_results if s.state == StepState.COMPLETED)

    @property
    def failed_steps_count(self) -> int:
        """Count of steps that failed."""
        return sum(1 for s in self.step_results if s.state == StepState.FAILED)

    @property
    def skipped_steps_count(self) -> int:
        """Count of steps that were skipped."""
        return sum(1 for s in self.step_results if s.state == StepState.SKIPPED)
