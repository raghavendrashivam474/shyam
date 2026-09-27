"""Integration tests for SurfaceCoordinator with ShyamRuntime."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from shyam.continuity.models import ContinuityOutcome, ContinuityResult
from shyam.core.config import ShyamSettings
from shyam.core.readiness import EcosystemReadiness, EcosystemReadinessChangedEvent
from shyam.core.runtime import ShyamRuntime
from shyam.surface.coordinator import SurfaceCoordinator
from shyam.surface.models import InteractionRequest, SurfaceState


@pytest.fixture
def runtime_settings(tmp_path) -> ShyamSettings:
    return ShyamSettings(
        data_directory=tmp_path / "data",
        runtime_name="test-surface-node",
        zarya_enabled=False,
        flux_enabled=False,
        discovery_enabled=False,
    )


@pytest.mark.asyncio
async def test_coordinator_degraded_when_runtime_not_ready(runtime_settings) -> None:
    runtime = ShyamRuntime(settings=runtime_settings)
    coordinator = SurfaceCoordinator(runtime=runtime)
    await coordinator.start()

    # If runtime is not ready, queries should return degraded
    req = InteractionRequest(text="continue this work on my other laptop")
    resp = await coordinator.handle_request(req)

    assert resp.state == SurfaceState.DEGRADED
    assert "ready" in resp.message.lower()


@pytest.mark.asyncio
async def test_coordinator_unknown_intent(runtime_settings) -> None:
    runtime = ShyamRuntime(settings=runtime_settings)
    coordinator = SurfaceCoordinator(runtime=runtime)
    await coordinator.start()

    # Direct override on the readiness tracker instance variable
    runtime.readiness_tracker._readiness = EcosystemReadiness.READY

    req = InteractionRequest(text="tell me a joke")
    resp = await coordinator.handle_request(req)

    assert resp.state == SurfaceState.IDLE
    assert "not sure" in resp.message.lower()


@pytest.mark.asyncio
async def test_coordinator_continuity_success(runtime_settings) -> None:
    runtime = ShyamRuntime(settings=runtime_settings)

    # Mock continuity service
    mock_continuity = MagicMock()
    mock_result = MagicMock(spec=ContinuityResult)
    mock_result.outcome = ContinuityOutcome.SUCCESS
    mock_continuity.request_continuity = AsyncMock(return_value=mock_result)

    runtime.continuity_service = mock_continuity

    coordinator = SurfaceCoordinator(runtime=runtime)
    await coordinator.start()

    # Direct override on the readiness tracker instance variable
    runtime.readiness_tracker._readiness = EcosystemReadiness.READY

    req = InteractionRequest(text="continue this work on my other laptop")
    resp = await coordinator.handle_request(req)

    assert resp.state == SurfaceState.COMPLETED
    assert "done" in resp.message.lower()
    mock_continuity.request_continuity.assert_awaited_once()


@pytest.mark.asyncio
async def test_coordinator_continuity_failure_handling(runtime_settings) -> None:
    runtime = ShyamRuntime(settings=runtime_settings)

    # Mock continuity service failure
    mock_continuity = MagicMock()
    mock_result = MagicMock(spec=ContinuityResult)
    mock_result.outcome = ContinuityOutcome.FAILED
    mock_continuity.request_continuity = AsyncMock(return_value=mock_result)

    runtime.continuity_service = mock_continuity

    coordinator = SurfaceCoordinator(runtime=runtime)
    await coordinator.start()

    # Direct override on the readiness tracker instance variable
    runtime.readiness_tracker._readiness = EcosystemReadiness.READY

    req = InteractionRequest(text="continue this work on my other laptop")
    resp = await coordinator.handle_request(req)

    assert resp.state == SurfaceState.FAILED
    assert "couldn't continue" in resp.message.lower()


@pytest.mark.asyncio
async def test_coordinator_readiness_event_reaction(runtime_settings) -> None:
    runtime = ShyamRuntime(settings=runtime_settings)
    coordinator = SurfaceCoordinator(runtime=runtime)
    await coordinator.start()

    # Initially not ready
    assert coordinator.current_state == SurfaceState.DEGRADED

    # Emit EcosystemReadinessChangedEvent -> READY
    event = EcosystemReadinessChangedEvent(
        source="tracker",
        old_readiness=EcosystemReadiness.STARTING,
        new_readiness=EcosystemReadiness.READY,
    )
    await runtime.events.publish(event)

    assert coordinator.current_state == SurfaceState.IDLE
