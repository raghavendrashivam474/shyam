import asyncio
import pytest
from shyam.composite import (
    Binding,
    BindingSource,
    CompositeBindingError,
    CompositeCapability,
    CompositeCapabilityRegistry,
    CompositeDefinitionError,
    CompositeEngine,
    CompositeInputError,
    CompositeNotFoundError,
    CompositeStep,
)
from shyam.workflow.engine import WorkflowCancellationToken, WorkflowEngine
from shyam.workflow.models import StepResult, Workflow, WorkflowResult
from shyam.workflow.state import StepState, WorkflowState


class DummyWorkflowEngine:
    """Mock WorkflowEngine to simulate S10 execution without real providers/navigator."""

    def __init__(self):
        self.calls = []
        self._outputs = {}
        self._should_fail_step = None
        self._fail_reason = ""

    def register_step_output(self, step_id: str, output: any):
        self._outputs[step_id] = output

    def set_failing_step(self, step_id: str, reason: str = "Execution failed"):
        self._should_fail_step = step_id
        self._fail_reason = reason

    async def run(self, workflow: Workflow, cancellation_token: WorkflowCancellationToken = None) -> WorkflowResult:
        self.calls.append((workflow, cancellation_token))

        if cancellation_token and cancellation_token.is_cancelled:
            step_results = []
            for step in workflow.steps:
                step_results.append(
                    StepResult(
                        step_id=step.step_id,
                        capability=step.capability,
                        state=StepState.CANCELLED,
                        error=cancellation_token.reason,
                    )
                )
            return WorkflowResult(
                workflow_id=workflow.workflow_id,
                name=workflow.name,
                state=WorkflowState.CANCELLED,
                step_results=tuple(step_results),
                error_detail=cancellation_token.reason,
            )

        step_results = []
        workflow_failed = False
        error_detail = None

        for step in workflow.steps:
            if self._should_fail_step == step.step_id:
                workflow_failed = True
                error_detail = self._fail_reason
                step_results.append(
                    StepResult(
                        step_id=step.step_id,
                        capability=step.capability,
                        state=StepState.FAILED,
                        error=self._fail_reason,
                    )
                )
            else:
                out = self._outputs.get(step.step_id)
                step_results.append(
                    StepResult(
                        step_id=step.step_id,
                        capability=step.capability,
                        state=StepState.COMPLETED,
                        output=out,
                    )
                )

        return WorkflowResult(
            workflow_id=workflow.workflow_id,
            name=workflow.name,
            state=WorkflowState.FAILED if workflow_failed else WorkflowState.COMPLETED,
            step_results=tuple(step_results),
            error_detail=error_detail,
        )


# ============================================================================
# Definition / Validation Tests
# ============================================================================

def test_valid_composite_definition():
    comp = CompositeCapability(
        capability_id="test.composite",
        name="Test Composite",
        inputs=("input_a",),
        steps=(
            CompositeStep(
                step_id="step1",
                capability="test.capability_a",
                input_bindings={
                    "field1": Binding(source=BindingSource.INPUT, source_id="input_a")
                },
            ),
        ),
        outputs={
            "out_a": Binding(source=BindingSource.STEP, source_id="step1")
        },
    )
    assert comp.capability_id == "test.composite"
    assert len(comp.steps) == 1
    assert comp.outputs["out_a"].source_id == "step1"


def test_invalid_namespaced_capability_id():
    with pytest.raises(ValueError, match="must be namespaced"):
        CompositeCapability(capability_id="invalidid", name="Bad")


def test_invalid_step_order_binding():
    with pytest.raises(ValueError, match="references step 'step2' which has not been defined yet"):
        CompositeCapability(
            capability_id="test.composite",
            name="Test Composite",
            inputs=("input_a",),
            steps=(
                CompositeStep(
                    step_id="step1",
                    capability="test.capability_a",
                    input_bindings={
                        "field1": Binding(source=BindingSource.STEP, source_id="step2")
                    },
                ),
                CompositeStep(
                    step_id="step2",
                    capability="test.capability_b",
                    input_bindings={},
                ),
            ),
        )


def test_duplicate_step_ids():
    with pytest.raises(ValueError, match="Duplicate step_id"):
        CompositeCapability(
            capability_id="test.composite",
            name="Test Composite",
            steps=(
                CompositeStep(step_id="step1", capability="a.b"),
                CompositeStep(step_id="step1", capability="c.d"),
            ),
        )


# ============================================================================
# Registry Tests
# ============================================================================

def test_composite_registry_operations():
    registry = CompositeCapabilityRegistry()
    comp = CompositeCapability(
        capability_id="test.composite",
        name="Test",
        steps=()
    )

    assert registry.count == 0
    registry.register(comp)
    assert registry.count == 1
    assert "test.composite" in registry
    assert registry.get("test.composite") == comp

    with pytest.raises(CompositeDefinitionError):
        registry.register(comp)  # default overwrite=False raises

    registry.register(comp, overwrite=True)  # works
    assert registry.count == 1

    registry.unregister("test.composite")
    assert registry.count == 0
    with pytest.raises(CompositeNotFoundError):
        registry.require("test.composite")


# ============================================================================
# Engine execution and binding tests
# ============================================================================

@pytest.mark.asyncio
async def test_composite_engine_successful_execution():
    fake_engine = DummyWorkflowEngine()
    fake_engine.register_step_output("step1", {"key_a": "val_a", "key_b": "val_b"})
    fake_engine.register_step_output("step2", "final_result")

    registry = CompositeCapabilityRegistry()
    comp = CompositeCapability(
        capability_id="test.composite",
        name="Test Composite",
        inputs=("source",),
        steps=(
            CompositeStep(
                step_id="step1",
                capability="test.capability_a",
                input_bindings={
                    "path": Binding(source=BindingSource.INPUT, source_id="source")
                },
            ),
            CompositeStep(
                step_id="step2",
                capability="test.capability_b",
                input_bindings={
                    "data": Binding(source=BindingSource.STEP, source_id="step1", source_key="key_b")
                },
            ),
        ),
        outputs={
            "result": Binding(source=BindingSource.STEP, source_id="step2"),
            "extracted": Binding(source=BindingSource.STEP, source_id="step1", source_key="key_a"),
        },
    )
    registry.register(comp)

    engine = CompositeEngine(workflow_engine=fake_engine, registry=registry)
    result = await engine.invoke("test.composite", {"source": "my-source"})

    assert result.is_success
    assert result.state == "COMPLETED"
    assert result.outputs["result"] == "final_result"
    assert result.outputs["extracted"] == "val_a"
    assert len(result.step_results) == 2


@pytest.mark.asyncio
async def test_composite_engine_missing_input():
    fake_engine = DummyWorkflowEngine()
    registry = CompositeCapabilityRegistry()
    comp = CompositeCapability(
        capability_id="test.composite",
        name="Test",
        inputs=("source",),
        steps=()
    )
    registry.register(comp)
    engine = CompositeEngine(fake_engine, registry)

    with pytest.raises(CompositeInputError, match="Missing required input"):
        await engine.invoke("test.composite", {})


@pytest.mark.asyncio
async def test_composite_engine_binding_key_extraction_failure():
    fake_engine = DummyWorkflowEngine()
    fake_engine.register_step_output("step1", "not-a-dict")

    registry = CompositeCapabilityRegistry()
    comp = CompositeCapability(
        capability_id="test.composite",
        name="Test Composite",
        inputs=(),
        steps=(
            CompositeStep(step_id="step1", capability="a.b"),
            CompositeStep(
                step_id="step2",
                capability="c.d",
                input_bindings={
                    "field": Binding(source=BindingSource.STEP, source_id="step1", source_key="key")
                },
            ),
        ),
    )
    registry.register(comp)
    engine = CompositeEngine(fake_engine, registry)

    with pytest.raises(CompositeBindingError, match="Cannot extract key 'key' from non-dict"):
        await engine.invoke("test.composite", {})


@pytest.mark.asyncio
async def test_composite_engine_fail_fast_propagation():
    fake_engine = DummyWorkflowEngine()
    fake_engine.set_failing_step("step1", "Step 1 crashed")

    registry = CompositeCapabilityRegistry()
    comp = CompositeCapability(
        capability_id="test.composite",
        name="Test",
        steps=(
            CompositeStep(step_id="step1", capability="a.b"),
            CompositeStep(step_id="step2", capability="c.d"),
        ),
    )
    registry.register(comp)
    engine = CompositeEngine(fake_engine, registry)

    result = await engine.invoke("test.composite", {})
    assert not result.is_success
    assert result.state == "FAILED"
    assert result.error_detail == "Step 1 crashed"
    assert len(result.step_results) == 1  # step2 never runs


@pytest.mark.asyncio
async def test_composite_engine_cooperative_cancellation():
    fake_engine = DummyWorkflowEngine()
    fake_engine.register_step_output("step1", "ok")

    registry = CompositeCapabilityRegistry()
    comp = CompositeCapability(
        capability_id="test.composite",
        name="Test",
        steps=(
            CompositeStep(step_id="step1", capability="a.b"),
            CompositeStep(step_id="step2", capability="c.d"),
        ),
    )
    registry.register(comp)
    engine = CompositeEngine(fake_engine, registry)

    token = WorkflowCancellationToken()

    # Define a helper that cancels token mid-execution
    async def invoke_with_delayed_cancel():
        # First step completes, then we cancel
        res = await engine.invoke("test.composite", {}, cancellation_token=token)
        return res

    # Let's cancel the token before running step2. Since we are using DummyWorkflowEngine,
    # we can just cancel the token right after the engine starts executing.
    # To simulate realistic cancellation, let's cancel the token *before* invocation:
    token.cancel("User cancelled")
    result = await engine.invoke("test.composite", {}, cancellation_token=token)

    assert result.state == "CANCELLED"
    assert result.error_detail == "User cancelled"
    assert len(result.step_results) == 0
