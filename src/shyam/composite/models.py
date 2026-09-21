"""Composite capability domain models - S11.

Frozen Pydantic models for defining reusable composite capabilities,
their step bindings, input/output contracts, and execution results.

A CompositeCapability is a reusable capability whose implementation
is a validated composition of existing primitive capabilities executed
through the S10 WorkflowEngine.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shyam.navigation.models import NavigationConstraints


# ---------------------------------------------------------------------------
# Binding model — deterministic, explicit, no DSL
# ---------------------------------------------------------------------------

class BindingSource(StrEnum):
    """Where a bound value originates."""

    INPUT = "input"
    """Value comes from the composite invocation input."""

    STEP = "step"
    """Value comes from a previous step's output."""


class Binding(BaseModel):
    """An explicit, deterministic data binding for a step input field.

    Bindings are resolved at instantiation time (for INPUT sources) or
    between steps (for STEP sources) by the CompositeEngine.

    No expressions, no scripting, no transformations.
    """

    model_config = ConfigDict(frozen=True)

    source: BindingSource = Field(
        ...,
        description="Whether the value comes from composite input or a prior step output.",
    )
    source_id: str = Field(
        ...,
        description="For INPUT: the input field name. For STEP: the step_id.",
    )
    source_key: str | None = Field(
        default=None,
        description=(
            "Optional key to extract from the source value. "
            "If None, the entire source value is used."
        ),
    )

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Binding source_id must be a non-empty string")
        return v.strip()


# ---------------------------------------------------------------------------
# Composite step
# ---------------------------------------------------------------------------

class CompositeStep(BaseModel):
    """A step within a composite capability definition.

    Unlike WorkflowStep (which carries concrete input_data), a CompositeStep
    carries *bindings* that are resolved at invocation time.
    """

    model_config = ConfigDict(frozen=True)

    step_id: str = Field(
        ...,
        description="Unique identifier for this step within the composite.",
    )
    capability: str = Field(
        ...,
        description="Namespaced capability ID to invoke (e.g. 'file.read').",
    )
    constraints: NavigationConstraints = Field(
        default_factory=NavigationConstraints,
        description="Optional S9 navigation constraints.",
    )
    input_bindings: dict[str, Binding] = Field(
        default_factory=dict,
        description=(
            "Maps each step input field name to a Binding that specifies "
            "where the value comes from."
        ),
    )
    description: str = Field(
        default="",
        description="Human-readable description of this step.",
    )

    @field_validator("step_id")
    @classmethod
    def validate_step_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Composite step_id must be a non-empty string")
        return v.strip()

    @field_validator("capability")
    @classmethod
    def validate_capability(cls, v: str) -> str:
        if not v or "." not in v:
            raise ValueError(
                f"Composite step capability must be namespaced (e.g. 'file.read'), got: '{v}'"
            )
        return v


# ---------------------------------------------------------------------------
# Composite capability definition
# ---------------------------------------------------------------------------

class CompositeCapability(BaseModel):
    """A reusable capability composed of existing primitive capabilities.

    The composite defines an input contract, an ordered sequence of bound
    steps, and an output contract. At invocation time the CompositeEngine
    resolves bindings, constructs S10 Workflows, and executes them through
    the existing WorkflowEngine.
    """

    model_config = ConfigDict(frozen=True)

    capability_id: str = Field(
        ...,
        description="Stable, namespaced identifier (e.g. 'file.copy').",
    )
    name: str = Field(
        ...,
        description="Human-readable name.",
    )
    version: str = Field(
        default="1.0.0",
        description="Semantic version string.",
    )
    description: str = Field(
        default="",
        description="What this composite capability does.",
    )
    inputs: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Ordered names of required invocation input fields.",
    )
    outputs: dict[str, Binding] = Field(
        default_factory=dict,
        description=(
            "Maps composite output field names to Bindings that extract "
            "values from step results or pass-through inputs."
        ),
    )
    steps: tuple[CompositeStep, ...] = Field(
        default_factory=tuple,
        description="Ordered sequence of constituent steps.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible metadata.",
    )

    @field_validator("capability_id")
    @classmethod
    def validate_capability_id(cls, v: str) -> str:
        if not v or "." not in v:
            raise ValueError(
                f"Composite capability_id must be namespaced (e.g. 'file.copy'), got: '{v}'"
            )
        parts = v.split(".")
        if any(not part.isidentifier() for part in parts):
            raise ValueError(
                f"Composite capability_id parts must be valid identifiers, got: '{v}'"
            )
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Composite name cannot be empty")
        return v.strip()

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        parts = v.split(".")
        if len(parts) < 1 or len(parts) > 3:
            raise ValueError(f"Version must be 1-3 dot-separated integers, got: '{v}'")
        for part in parts:
            if not part.isdigit():
                raise ValueError(f"Version parts must be non-negative integers, got: '{v}'")
        return v

    @model_validator(mode="after")
    def validate_step_references(self) -> "CompositeCapability":
        """Ensure output bindings reference valid step IDs and step bindings
        only reference earlier steps or declared inputs."""
        step_ids: set[str] = set()
        for step in self.steps:
            if step.step_id in step_ids:
                raise ValueError(f"Duplicate step_id in composite: '{step.step_id}'")
            step_ids.add(step.step_id)

            # Validate step input bindings
            for field_name, binding in step.input_bindings.items():
                if binding.source == BindingSource.INPUT:
                    if binding.source_id not in self.inputs:
                        raise ValueError(
                            f"Step '{step.step_id}' field '{field_name}' binds to "
                            f"undeclared input '{binding.source_id}'"
                        )
                elif binding.source == BindingSource.STEP:
                    if binding.source_id not in step_ids:
                        raise ValueError(
                            f"Step '{step.step_id}' field '{field_name}' references "
                            f"step '{binding.source_id}' which has not been defined yet "
                            f"(steps are ordered; only prior steps may be referenced)"
                        )

        # Validate output bindings
        for out_name, binding in self.outputs.items():
            if binding.source == BindingSource.INPUT:
                if binding.source_id not in self.inputs:
                    raise ValueError(
                        f"Output '{out_name}' binds to undeclared input '{binding.source_id}'"
                    )
            elif binding.source == BindingSource.STEP:
                if binding.source_id not in step_ids:
                    raise ValueError(
                        f"Output '{out_name}' references unknown step '{binding.source_id}'"
                    )

        return self


# ---------------------------------------------------------------------------
# Composite execution result
# ---------------------------------------------------------------------------

class CompositeResult(BaseModel):
    """Immutable aggregate outcome of a composite capability invocation."""

    model_config = ConfigDict(frozen=True)

    capability_id: str = Field(description="The composite that was invoked.")
    state: str = Field(description="Terminal state: COMPLETED, FAILED, CANCELLED.")
    outputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Resolved output values per the composite's output contract.",
    )
    step_results: tuple[Any, ...] = Field(
        default_factory=tuple,
        description="Ordered StepResult objects from the underlying S10 executions.",
    )
    error_detail: str | None = Field(
        default=None,
        description="Error description if the composite failed.",
    )

    @property
    def is_success(self) -> bool:
        return self.state == "COMPLETED"
