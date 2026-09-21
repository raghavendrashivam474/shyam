"""Composite capability exception hierarchy - S11.

Extends the S10 WorkflowError base so composite errors integrate
with the existing error handling surface.
"""

from __future__ import annotations

from shyam.workflow.errors import WorkflowError


class CompositeError(WorkflowError):
    """Base exception for composite capability subsystem errors."""


class CompositeDefinitionError(CompositeError):
    """Raised when a composite capability definition is structurally invalid."""

    def __init__(self, capability_id: str, reason: str) -> None:
        super().__init__(f"Invalid composite definition '{capability_id}': {reason}")
        self.capability_id = capability_id
        self.reason = reason


class CompositeInputError(CompositeError):
    """Raised when invocation inputs violate the composite's input contract."""

    def __init__(self, capability_id: str, reason: str) -> None:
        super().__init__(f"Invalid input for composite '{capability_id}': {reason}")
        self.capability_id = capability_id
        self.reason = reason


class CompositeBindingError(CompositeError):
    """Raised when a data binding reference cannot be resolved."""

    def __init__(self, step_id: str, field: str, reason: str) -> None:
        super().__init__(
            f"Binding resolution failed for step '{step_id}' field '{field}': {reason}"
        )
        self.step_id = step_id
        self.field = field
        self.reason = reason


class CompositeNotFoundError(CompositeError):
    """Raised when a referenced composite capability is not registered."""

    def __init__(self, capability_id: str) -> None:
        super().__init__(f"Composite capability '{capability_id}' not found in registry.")
        self.capability_id = capability_id
