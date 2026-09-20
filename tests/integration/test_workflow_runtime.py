"""Integration tests for Workflow Engine run inside active ShyamRuntime."""

import asyncio
from pathlib import Path
import pytest

from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime
from shyam.workflow.models import Workflow, WorkflowStep
from shyam.workflow.state import WorkflowState


@pytest.mark.asyncio
async def test_runtime_workflow_execution_integration(tmp_path):
    """Proves end-to-end multi-step workflow inside active ShyamRuntime.

    Executes:
    1. Write file content locally via local.filesystem (file.write)
    2. Read file content locally via local.filesystem (file.read)
    """
    settings = ShyamSettings(
        data_directory=tmp_path / "shyam_data",
        discovery_enabled=False,
        zarya_enabled=False,
        flux_enabled=False,
    )

    test_file = tmp_path / "integration_flow.txt"

    async with ShyamRuntime(settings=settings) as runtime:
        assert runtime.is_running is True

        # Construct a 2-step document creation & validation workflow
        wf = Workflow(
            name="integration-doc-flow",
            steps=(
                WorkflowStep(
                    step_id="write-doc",
                    capability="file.write",
                    input_data={"path": str(test_file), "content": "Integration Test Content!"},
                ),
                WorkflowStep(
                    step_id="read-doc",
                    capability="file.read",
                    input_data={"path": str(test_file)},
                ),
            ),
        )

        # Run the workflow on the runtime
        result = await runtime.run_workflow(wf)

        # Validate aggregate result and sequential step side effects
        assert result.is_success is True
        assert result.state == WorkflowState.COMPLETED
        assert result.completed_steps_count == 2
        
        # Verify first step outputs
        assert result.step_results[0].step_id == "write-doc"
        assert result.step_results[0].output["written_bytes"] > 0
        assert test_file.exists()

        # Verify second step outputs
        assert result.step_results[1].step_id == "read-doc"
        assert result.step_results[1].output["content"] == "Integration Test Content!"
