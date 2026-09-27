"""Integration tests for ShyamRuntime startup, ordering, and readiness lifecycle (S17.5)."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.core.config import ShyamSettings
from shyam.core.readiness import ComponentState, EcosystemReadiness
from shyam.core.runtime import ShyamRuntime
from shyam.providers.model import Provider


@pytest.fixture
def tmp_settings(tmp_path) -> ShyamSettings:
    return ShyamSettings(
        environment="testing",
        data_directory=tmp_path / "runtime_data",
        runtime_name="test-shyam-node",
        discovery_enabled=False,  # Keep isolated from local UDP network
        readiness_poll_interval=0.05,
    )


@pytest.mark.asyncio
async def test_runtime_startup_with_all_components_ready(tmp_settings: ShyamSettings) -> None:
    """ShyamRuntime starts up and transitions to RUNNING, and readiness becomes READY when components respond."""
    runtime = ShyamRuntime(settings=tmp_settings)

    with patch.object(runtime.zarya_provider, "connect", return_value=True), \
         patch.object(runtime.zarya_provider, "refresh_status", return_value=AvailabilityStatus.AVAILABLE), \
         patch.object(runtime.flux_provider, "connect", return_value=True), \
         patch.object(runtime.flux_provider, "refresh_status", return_value=AvailabilityStatus.AVAILABLE):

        async with runtime:
            assert runtime.is_running
            # Allow background readiness tracker to poll
            await asyncio.sleep(0.1)

            assert runtime.readiness == EcosystemReadiness.READY
            snapshot = runtime.get_readiness_snapshot()
            assert snapshot.is_ready
            assert snapshot.components["node"].state == ComponentState.READY
            assert snapshot.components["zarya"].state == ComponentState.READY
            assert snapshot.components["flux"].state == ComponentState.READY


@pytest.mark.asyncio
async def test_runtime_startup_with_delayed_components(tmp_settings: ShyamSettings) -> None:
    """Shyam starts even if Zarya and Flux are not ready yet, and reaches READY when they come online."""
    runtime = ShyamRuntime(settings=tmp_settings)

    # Initial state: both components fail connection
    zarya_connected = False
    flux_connected = False

    def mock_zarya_connect():
        nonlocal zarya_connected
        return zarya_connected

    def mock_flux_connect():
        nonlocal flux_connected
        return flux_connected

    with patch.object(runtime.zarya_provider, "connect", side_effect=mock_zarya_connect), \
         patch.object(runtime.zarya_provider, "refresh_status", return_value=AvailabilityStatus.AVAILABLE), \
         patch.object(runtime.flux_provider, "connect", side_effect=mock_flux_connect), \
         patch.object(runtime.flux_provider, "refresh_status", return_value=AvailabilityStatus.AVAILABLE):

        async with runtime:
            assert runtime.is_running
            await asyncio.sleep(0.08)

            # Initially DEGRADED
            assert runtime.readiness == EcosystemReadiness.DEGRADED

            # Flux starts up after delay
            flux_connected = True
            await asyncio.sleep(0.08)
            assert runtime.get_readiness_snapshot().components["flux"].state == ComponentState.READY

            # Zarya starts up after delay
            zarya_connected = True
            await asyncio.sleep(0.08)
            assert runtime.get_readiness_snapshot().components["zarya"].state == ComponentState.READY

            # Ecosystem is now fully READY
            assert runtime.readiness == EcosystemReadiness.READY


@pytest.mark.asyncio
async def test_runtime_repeated_lifecycle(tmp_settings: ShyamSettings) -> None:
    """Starting and stopping runtime repeatedly does not corrupt state or leave leaked background tasks."""
    runtime = ShyamRuntime(settings=tmp_settings)

    with patch.object(runtime.zarya_provider, "connect", return_value=True), \
         patch.object(runtime.flux_provider, "connect", return_value=True):

        # First cycle
        async with runtime:
            assert runtime.is_running
            await asyncio.sleep(0.05)
        assert not runtime.is_running
        assert runtime.readiness_tracker._poll_task is None

        # Reset state transition for testing repeated start
        from shyam.core.runtime import LifecycleState
        runtime.state.status = LifecycleState.CREATED

        # Second cycle
        async with runtime:
            assert runtime.is_running
            await asyncio.sleep(0.05)
        assert not runtime.is_running
        assert runtime.readiness_tracker._poll_task is None


@pytest.mark.asyncio
async def test_runtime_standalone_mode_without_external_components(tmp_path) -> None:
    """When external components are disabled, ShyamRuntime achieves READY state standalone."""
    standalone_settings = ShyamSettings(
        environment="testing",
        data_directory=tmp_path / "standalone_data",
        zarya_enabled=False,
        flux_enabled=False,
        discovery_enabled=False,
        readiness_poll_interval=0.05,
    )

    runtime = ShyamRuntime(settings=standalone_settings)

    async with runtime:
        await asyncio.sleep(0.08)
        assert runtime.readiness == EcosystemReadiness.READY
        snapshot = runtime.get_readiness_snapshot()
        assert snapshot.is_ready
        assert "zarya" not in snapshot.components
        assert "flux" not in snapshot.components
        assert snapshot.components["node"].state == ComponentState.READY
