"""End-to-End Continuity Integration Tests via Shyam Visual UI."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

import shyam.ui.window
from shyam.continuity.models import ContinuityOutcome, ContinuityResult, ContinuitySession, ContinuityState
from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime
from shyam.surface.coordinator import SurfaceCoordinator


@pytest.mark.asyncio
async def test_ui_continuity_success_flow(tk_root):
    """Verify that 'continue this work on my other laptop' via the UI executes through coordinator and updates UI to SUCCESS."""
    settings = ShyamSettings(
        environment="testing",
        discovery_enabled=False,
        flux_enabled=False,
        zarya_enabled=False,
    )
    runtime = ShyamRuntime(settings=settings)

    async with runtime:
        # Mock continuity service on runtime
        mock_session = MagicMock(spec=ContinuitySession)
        mock_session.result = ContinuityResult(
            session_id="session-ui-123",
            work_id="work-active-surface",
            target_device_id="remote-node-1",
            outcome=ContinuityOutcome.SUCCESS,
        )
        mock_session.state = ContinuityState.COMPLETED

        mock_continuity = MagicMock()
        mock_continuity.request_continuity = AsyncMock(return_value=mock_session)
        runtime.continuity_service = mock_continuity

        coordinator = SurfaceCoordinator(runtime=runtime)
        await coordinator.start()

        window = shyam.ui.window.ShyamWindow(
            root=tk_root,
            coordinator=coordinator,
            loop=asyncio.get_running_loop(),
        )
        tk_root.update()

        # Submit continuity command
        window.input_entry.insert(0, "continue this work on my other laptop")
        window.submit_input()

        # Let async task and Tkinter event queue settle
        await asyncio.sleep(0.05)
        tk_root.update()

        # Verify continuity was called with expected work request
        mock_continuity.request_continuity.assert_called_once()

        # Verify visual output
        assert window.symbol_label.cget("text") == "✓"
        assert window.state_label.cget("text") == "Completed"
        assert "done — work continued on your other laptop" in window.message_label.cget("text").lower()
        assert window._is_busy is False


@pytest.mark.asyncio
async def test_ui_continuity_failure_flow(tk_root):
    """Verify that a failed continuity session renders human-facing failure in the UI."""
    settings = ShyamSettings(
        environment="testing",
        discovery_enabled=False,
        flux_enabled=False,
        zarya_enabled=False,
    )
    runtime = ShyamRuntime(settings=settings)

    async with runtime:
        # Mock continuity failure
        mock_session = MagicMock(spec=ContinuitySession)
        mock_session.result = ContinuityResult(
            session_id="session-ui-fail",
            work_id="work-active-surface",
            target_device_id="remote-node-1",
            outcome=ContinuityOutcome.FAILED,
        )
        mock_session.state = ContinuityState.FAILED

        mock_continuity = MagicMock()
        mock_continuity.request_continuity = AsyncMock(return_value=mock_session)
        runtime.continuity_service = mock_continuity

        coordinator = SurfaceCoordinator(runtime=runtime)
        await coordinator.start()

        window = shyam.ui.window.ShyamWindow(
            root=tk_root,
            coordinator=coordinator,
            loop=asyncio.get_running_loop(),
        )
        tk_root.update()

        # Submit continuity command
        window.input_entry.insert(0, "continue this work on my other laptop")
        window.submit_input()

        # Let async task and Tkinter event queue settle
        await asyncio.sleep(0.05)
        tk_root.update()

        # Verify visual output
        assert window.symbol_label.cget("text") == "✕"
        assert window.state_label.cget("text") == "Unable to complete"
        assert "couldn't continue" in window.message_label.cget("text").lower()
        assert window._is_busy is False