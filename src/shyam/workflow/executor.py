"""Execution boundary protocol and registry - S10.

Decouples the WorkflowEngine from concrete provider invocation mechanisms.
The WorkflowEngine asks the ExecutorRegistry for a CapabilityExecutor matching
the provider selected by the S9 Hybrid Navigator.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from shyam.navigation.models import NavigationCandidate
from shyam.workflow.errors import ExecutorNotFoundError

logger = logging.getLogger("shyam.workflow.executor")


@runtime_checkable
class CapabilityExecutor(Protocol):
    """Protocol for provider-specific execution adapters.

    An executor receives the target candidate selected by S9 Navigator,
    together with structured input data, and invokes the underlying provider.
    """

    async def execute(
        self,
        target: NavigationCandidate,
        input_data: dict[str, Any],
    ) -> Any:
        """Execute a capability on the target provider.

        Args:
            target: The candidate triple (node, provider, capability) chosen by S9.
            input_data: Structured arguments passed to the provider.

        Returns:
            Provider output on success (any JSON-serializable structure or primitive).

        Raises:
            StepExecutionError or underlying provider exceptions on failure.
        """
        ...


class ExecutorRegistry:
    """Registry mapping provider_id -> CapabilityExecutor adapter."""

    def __init__(self) -> None:
        self._executors: dict[str, CapabilityExecutor] = {}

    def register(self, provider_id: str, executor: CapabilityExecutor) -> None:
        """Register an execution adapter for a specific provider_id."""
        self._executors[provider_id] = executor
        logger.debug("Registered executor adapter for provider '%s'", provider_id)

    def unregister(self, provider_id: str) -> CapabilityExecutor | None:
        """Unregister an executor adapter."""
        return self._executors.pop(provider_id, None)

    def get(self, provider_id: str) -> CapabilityExecutor:
        """Retrieve the executor adapter for a provider_id.

        Raises:
            ExecutorNotFoundError: If no executor is registered for provider_id.
        """
        executor = self._executors.get(provider_id)
        if executor is None:
            raise ExecutorNotFoundError(provider_id)
        return executor

    def contains(self, provider_id: str) -> bool:
        """Check if an executor is registered for the provider_id."""
        return provider_id in self._executors

    def __contains__(self, provider_id: str) -> bool:
        return self.contains(provider_id)
