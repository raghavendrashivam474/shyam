"""Unit tests for S12 Ecosystem State and Context subsystem."""

from datetime import UTC, datetime
import pytest
from pydantic import ValidationError

from shyam.capabilities.model import AvailabilityStatus
from shyam.context import (
    ActiveWorkItem,
    ActivityKind,
    EcosystemContext,
    EcosystemState,
    EcosystemStateStore,
    RecentActivityEntry,
    WorkStatus,
)
from shyam.context.service import EcosystemContextService
from shyam.core.runtime import ShyamRuntime
from shyam.discovery.ecosystem_models import (
    DiscoveredNode,
    EcosystemNodeDiscoveredEvent,
    EcosystemNodeLostEvent,
    EcosystemNodeStaleEvent,
    EcosystemNodeState,
    EcosystemNodeUpdatedEvent,
    EcosystemSnapshot,
)
from shyam.events.bus import EventBus
from shyam.navigation.models import NavigationCandidate
from shyam.workflow.events import (
    WorkflowCancelledEvent,
    WorkflowCompletedEvent,
    WorkflowFailedEvent,
    WorkflowStartedEvent,
    WorkflowStepStartedEvent,
)


def test_immutable_state_models() -> None:
    """Verify that models are immutable and serialize correctly."""
    snap = EcosystemSnapshot(local_node_id="local_node", nodes={})
    state = EcosystemState(
        version=1,
        discovery=snap,
        active_work=(),
        recent_activity=(),
    )
    assert state.version == 1
    assert state.total_nodes == 0
    assert state.running_work_count == 0

    with pytest.raises(ValidationError):
        # Should raise an error because model is frozen/immutable
        state.version = 2  # type: ignore


@pytest.mark.asyncio
async def test_store_ecosystem_event_handling() -> None:
    """Verify that state store successfully registers ecosystem state change events."""
    store = EcosystemStateStore()

    # Initial state check
    state = await store.get_state()
    assert state.version == 0
    assert len(state.recent_activity) == 0

    node = DiscoveredNode(
        node_id="node-123",
        node_name="Test Node",
        state=EcosystemNodeState.AVAILABLE,
    )

    # Trigger Node Discovered
    await store.on_node_discovered(EcosystemNodeDiscoveredEvent(node=node))
    state = await store.get_state()
    assert state.version == 1
    assert len(state.recent_activity) == 1
    assert state.recent_activity[0].kind == ActivityKind.NODE_DISCOVERED
    assert state.recent_activity[0].related_node_id == "node-123"

    # Trigger Node Updated
    await store.on_node_updated(
        EcosystemNodeUpdatedEvent(node=node, previous_state=EcosystemNodeState.KNOWN)
    )
    state = await store.get_state()
    assert state.version == 2
    assert state.recent_activity[0].kind == ActivityKind.NODE_UPDATED

    # Trigger Node Stale
    await store.on_node_stale(
        EcosystemNodeStaleEvent(
            node_id="node-123",
            node_name="Test Node",
            last_seen=datetime.now(UTC),
        )
    )
    state = await store.get_state()
    assert state.version == 3
    assert state.recent_activity[0].kind == ActivityKind.NODE_STALE

    # Trigger Node Lost
    await store.on_node_lost(
        EcosystemNodeLostEvent(
            node_id="node-123",
            node_name="Test Node",
            last_seen=datetime.now(UTC),
        )
    )
    state = await store.get_state()
    assert state.version == 4
    assert state.recent_activity[0].kind == ActivityKind.NODE_LOST


@pytest.mark.asyncio
async def test_store_workflow_lifecycle() -> None:
    """Verify state store maps started, step targets, and completed workflows."""
    store = EcosystemStateStore()

    # 1. Start workflow
    await store.on_workflow_started(
        WorkflowStartedEvent(
            workflow_id="wf-abc",
            workflow_name="Deploy App",
            step_count=3,
        )
    )

    state = await store.get_state()
    assert state.running_work_count == 1
    assert state.active_work[0].workflow_id == "wf-abc"
    assert state.active_work[0].status == WorkStatus.RUNNING
    assert state.active_work[0].step_count == 3
    assert state.active_work[0].target_node_id is None

    # 2. Enrich workflow step target node/provider information
    candidate = NavigationCandidate(
        node_id="target-node-1",
        node_name="Worker Node 1",
        provider_id="target-provider-1",
        provider_name="Docker Runner",
        capability_id="exec",
        is_local=False,
        node_state=EcosystemNodeState.AVAILABLE,
        provider_status=AvailabilityStatus.AVAILABLE,
        capability_availability=AvailabilityStatus.AVAILABLE,
    )
    await store.on_step_started(
        WorkflowStepStartedEvent(
            workflow_id="wf-abc",
            workflow_name="Deploy App",
            step_id="step-1",
            capability="exec",
            target=candidate,
        )
    )

    state = await store.get_state()
    assert state.active_work[0].target_node_id == "target-node-1"
    assert state.active_work[0].target_provider_id == "target-provider-1"

    # 3. Complete workflow
    await store.on_workflow_completed(
        WorkflowCompletedEvent(
            workflow_id="wf-abc",
            workflow_name="Deploy App",
            completed_steps_count=3,
        )
    )

    state = await store.get_state()
    assert state.running_work_count == 0  # Cleared from active tracking
    assert len(state.recent_activity) == 2
    assert state.recent_activity[0].kind == ActivityKind.WORKFLOW_COMPLETED


@pytest.mark.asyncio
async def test_context_service_lifecycle() -> None:
    """Verify service correctly subscribes/unsubscribes and acts as broker."""
    bus = EventBus()
    from shyam.discovery.ecosystem_registry import EcosystemRegistry

    registry = EcosystemRegistry(event_bus=bus)
    store = EcosystemStateStore()
    service = EcosystemContextService(registry=registry, event_bus=bus, store=store)

    assert not service._subscribed
    await service.start()
    assert service._subscribed

    # Feed an event through event bus
    node = DiscoveredNode(
        node_id="node-xyz",
        node_name="Remote Peer",
        state=EcosystemNodeState.AVAILABLE,
    )
    await bus.publish(EcosystemNodeDiscoveredEvent(node=node))

    state = await store.get_state()
    # The discovery snapshot inside state store should be updated and version incremented
    assert state.version > 0
    assert len(state.recent_activity) == 1
    assert state.recent_activity[0].kind == ActivityKind.NODE_DISCOVERED

    await service.stop()
    assert not service._subscribed


@pytest.mark.asyncio
async def test_runtime_context_apis() -> None:
    """Verify core ShyamRuntime endpoints provide state and context."""
    async with ShyamRuntime() as rt:
        state = await rt.get_ecosystem_state()
        context = await rt.get_ecosystem_context()

        assert isinstance(state, EcosystemState)
        assert isinstance(context, EcosystemContext)

        # Check local node identity represents correctly in discovery state
        assert context.local_node_id != "unknown"
        assert state.total_nodes >= 1
        assert not context.has_active_work
