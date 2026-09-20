"""Workflow and execution exception hierarchy - S10."""

from __future__ import annotations


class WorkflowError(Exception):
    """Base exception for workflow subsystem errors."""


class WorkflowExecutionError(WorkflowError):
    """Raised when an unrecoverable error occurs during workflow coordination."""


class StepExecutionError(WorkflowError):
    """Raised when a specific step execution fails on a provider."""

    def __init__(self, step_id: str, capability: str, reason: str) -> None:
        super().__init__(f"Step '{step_id}' ({capability}) execution failed: {reason}")
        self.step_id = step_id
        self.capability = capability
        self.reason = reason


class ExecutorNotFoundError(WorkflowError):
    """Raised when no executor is registered for a target provider ID."""

    def __init__(self, provider_id: str) -> None:
        super().__init__(f"No CapabilityExecutor registered for provider '{provider_id}'.")
        self.provider_id = provider_id


class NavigationTargetNotFoundError(WorkflowError):
    """Raised when S9 Hybrid Navigator fails to resolve an eligible target candidate."""

    def __init__(self, capability: str, reason: str = "") -> None:
        super().__init__(
            f"Navigation failed to resolve target for capability '{capability}'. Reason: {reason}"
        )
        self.capability = capability
        self.reason = reason
