"""Zarya Sovereign Agent Execution Adapter - S10.

Adapts S10 execution calls to the public ZaryaProvider.execute() interface.
"""

from __future__ import annotations

import asyncio
from typing import Any

from shyam.navigation.models import NavigationCandidate
from shyam.providers.zarya.provider import ZaryaProvider
from shyam.workflow.errors import StepExecutionError


class ZaryaExecutor:
    """Executes operations on a sovereign Zarya instance."""

    def __init__(self, provider: ZaryaProvider) -> None:
        self._provider = provider

    async def execute(
        self,
        target: NavigationCandidate,
        input_data: dict[str, Any],
    ) -> Any:
        """Invoke ZaryaProvider.execute() using tool name and arguments."""
        tool_name = input_data.get("tool", target.capability_id)
        args = input_data.get("args", {k: v for k, v in input_data.items() if k != "tool"})

        loop = asyncio.get_running_loop()

        try:
            # ZaryaProvider.execute is synchronous HTTP call, run in executor
            response = await loop.run_in_executor(
                None,
                self._provider.execute,
                tool_name,
                args,
            )
            return response.model_dump()
        except Exception as exc:
            raise StepExecutionError(
                step_id="unknown",
                capability=target.capability_id,
                reason=str(exc),
            ) from exc
