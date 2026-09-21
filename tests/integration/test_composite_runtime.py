import pytest
from shyam.composite import Binding, BindingSource, CompositeCapability, CompositeStep
from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime
from shyam.navigation.models import NavigationCandidate
from shyam.workflow.executor import CapabilityExecutor


class DummyLocalExecutor(CapabilityExecutor):
    """Simple integration executor that simulates local filesystem provider logic."""

    def __init__(self):
        self.history = []

    async def execute(self, target: NavigationCandidate, input_data: dict) -> dict:
        self.history.append((target, input_data))
        if target.capability_id == "file.read":
            return {"content": "shyam-integration-data"}
        elif target.capability_id == "file.write":
            return {"bytes_written": len(input_data.get("content", ""))}
        return {}


@pytest.mark.asyncio
async def test_runtime_composite_integration_vertical_slice():
    # 1. Setup runtime
    settings = ShyamSettings(discovery_enabled=False)
    async with ShyamRuntime(settings=settings) as runtime:
        # Override the executors with our dummy executor for test stability
        dummy_executor = DummyLocalExecutor()
        runtime.executor_registry.register("local.filesystem", dummy_executor)

        # 2. Register composite definition
        composite = CompositeCapability(
            capability_id="file.copy",
            name="Integrated File Copy",
            inputs=("source_path", "dest_path"),
            steps=(
                CompositeStep(
                    step_id="read_file",
                    capability="file.read",
                    input_bindings={
                        "path": Binding(source=BindingSource.INPUT, source_id="source_path")
                    },
                ),
                CompositeStep(
                    step_id="write_file",
                    capability="file.write",
                    input_bindings={
                        "path": Binding(source=BindingSource.INPUT, source_id="dest_path"),
                        "content": Binding(source=BindingSource.STEP, source_id="read_file", source_key="content"),
                    },
                ),
            ),
            outputs={
                "copied_bytes": Binding(source=BindingSource.STEP, source_id="write_file", source_key="bytes_written")
            },
        )
        runtime.composites.register(composite)

        # 3. Invoke composite through runtime
        inputs = {"source_path": "/test/src.txt", "dest_path": "/test/dest.txt"}
        result = await runtime.invoke_composite("file.copy", inputs)

        # 4. Assertions
        assert result.is_success
        assert result.state == "COMPLETED"
        assert result.outputs["copied_bytes"] == len("shyam-integration-data")
        assert len(result.step_results) == 2
        assert len(dummy_executor.history) == 2
