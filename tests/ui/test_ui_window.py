"""Unit tests for Shyam Tkinter visual window."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from shyam.surface.coordinator import SurfaceCoordinator
from shyam.surface.models import InteractionRequest, InteractionResponse, SurfaceState
from shyam.ui.window import STATE_CONFIG, ShyamWindow


@pytest.fixture
def mock_coordinator():
    coord = MagicMock(spec=SurfaceCoordinator)
    coord.current_state = SurfaceState.IDLE
    coord.get_status_message.return_value = "● Shyam is ready"
    coord.handle_request = AsyncMock(
        return_value=InteractionResponse(
            message="Done — work continued on your other laptop.",
            state=SurfaceState.COMPLETED,
        )
    )
    return coord


def test_ui_window_initialization(tk_root, mock_coordinator):
    """Test window builds successfully and renders initial state."""
    window = ShyamWindow(root=tk_root, coordinator=mock_coordinator)
    tk_root.update()

    assert window.title_label.cget("text") == "Shyam"
    assert window.symbol_label.cget("text") == "●"
    assert window.state_label.cget("text") == "Ready to help"
    assert "ready" in window.message_label.cget("text")


def test_ui_window_state_transitions(tk_root, mock_coordinator):
    """Test that all surface states transition the visuals properly."""
    window = ShyamWindow(root=tk_root, coordinator=mock_coordinator)

    # Degraded state
    window.update_state(SurfaceState.DEGRADED, message="Ecosystem unavailable")
    tk_root.update()
    assert window.symbol_label.cget("text") == "△"
    assert window.state_label.cget("text") == "Ecosystem degraded"
    assert window.message_label.cget("text") == "Ecosystem unavailable"

    # Executing state (disables input)
    window.update_state(SurfaceState.EXECUTING, message="Continuing your work...")
    tk_root.update()
    assert window.symbol_label.cget("text") == "◌"
    assert str(window.submit_button.cget("state")) == "disabled"
    assert window._is_busy is True

    # Completed state (re-enables input)
    window.update_state(SurfaceState.COMPLETED, message="Done!")
    tk_root.update()
    assert window.symbol_label.cget("text") == "✓"
    assert str(window.submit_button.cget("state")) == "normal"
    assert window._is_busy is False


def test_ui_window_submit_input(tk_root, mock_coordinator):
    """Test typing text and submitting dispatches to coordinator."""
    window = ShyamWindow(root=tk_root, coordinator=mock_coordinator)

    window.input_entry.insert(0, "continue this work on my other laptop")
    window.submit_input()
    tk_root.update()

    # Coordinator was called
    mock_coordinator.handle_request.assert_called_once()
    called_req = mock_coordinator.handle_request.call_args[0][0]
    assert isinstance(called_req, InteractionRequest)
    assert called_req.text == "continue this work on my other laptop"
    assert called_req.source == "text"

    # Outcome displayed
    assert window.symbol_label.cget("text") == "✓"
    assert "work continued" in window.message_label.cget("text")


def test_ui_window_handles_failure(tk_root, mock_coordinator):
    """Test failure response from coordinator updates UI to failed state."""
    mock_coordinator.handle_request = AsyncMock(
        return_value=InteractionResponse(
            message="I couldn't continue this work right now.",
            state=SurfaceState.FAILED,
            detail="Node unreachable",
        )
    )
    window = ShyamWindow(root=tk_root, coordinator=mock_coordinator)

    window.input_entry.insert(0, "continue work")
    window.submit_input()
    tk_root.update()

    assert window.symbol_label.cget("text") == "✕"
    assert window.state_label.cget("text") == "Unable to complete"
    assert "couldn't continue" in window.message_label.cget("text")