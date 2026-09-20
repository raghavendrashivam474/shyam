"""Flux Connectivity Gateway Execution Adapter - S10.

Adapts S10 execution calls to the public FluxProvider operations.
"""

from __future__ import annotations

import asyncio
from typing import Any

from shyam.navigation.models import NavigationCandidate
from shyam.providers.flux.provider import FluxProvider
from shyam.workflow.errors import StepExecutionError


class FluxExecutor:
    """Executes operations on an Aryntra Flux connectivity gateway."""

    def __init__(self, provider: FluxProvider) -> None:
        self._provider = provider

    async def execute(
        self,
        target: NavigationCandidate,
        input_data: dict[str, Any],
    ) -> Any:
        """Dispatch capability to corresponding FluxProvider method."""
        cap = target.capability_id
        loop = asyncio.get_running_loop()

        try:
            if cap == "flux.peer.discover":
                peers = await loop.run_in_executor(None, self._provider.discover_peers)
                return [p.model_dump() for p in peers]

            elif cap == "flux.peer.connect":
                peer_id = input_data.get("peer_id")
                if not peer_id:
                    raise ValueError("Missing 'peer_id' in input_data")
                res = await loop.run_in_executor(None, self._provider.connect_peer, peer_id)
                return res.model_dump()

            elif cap == "flux.transfer.send":
                peer_id = input_data.get("peer_id")
                artifact_path = input_data.get("artifact_path")
                if not peer_id or not artifact_path:
                    raise ValueError("Missing 'peer_id' or 'artifact_path' in input_data")
                res = await loop.run_in_executor(
                    None,
                    self._provider.transfer,
                    peer_id,
                    artifact_path,
                    input_data.get("artifact_name"),
                    input_data.get("is_directory", False),
                )
                return res.model_dump()

            elif cap == "flux.transfer.status":
                transfer_id = input_data.get("transfer_id")
                if not transfer_id:
                    raise ValueError("Missing 'transfer_id' in input_data")
                res = await loop.run_in_executor(None, self._provider.get_transfer_status, transfer_id)
                return res.model_dump()

            elif cap == "flux.transfer.cancel":
                transfer_id = input_data.get("transfer_id")
                if not transfer_id:
                    raise ValueError("Missing 'transfer_id' in input_data")
                res = await loop.run_in_executor(None, self._provider.cancel_transfer, transfer_id)
                return res.model_dump()

            else:
                raise StepExecutionError(
                    step_id="unknown",
                    capability=cap,
                    reason=f"Unsupported Flux capability: '{cap}'",
                )
        except Exception as exc:
            if isinstance(exc, StepExecutionError):
                raise
            raise StepExecutionError(
                step_id="unknown",
                capability=cap,
                reason=str(exc),
            ) from exc
