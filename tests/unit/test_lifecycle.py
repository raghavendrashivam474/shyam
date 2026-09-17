"""Unit tests for runtime lifecycle transitions and state management."""

import pytest

from shyam.core.lifecycle import InvalidStateTransitionError, LifecycleState
from shyam.core.state import RuntimeState


def test_valid_lifecycle_progression():
    """Verify normal runtime state lifecycle flow."""
    state = RuntimeState()
    assert state.status == LifecycleState.CREATED
    assert state.started_at is None
    assert state.stopped_at is None

    state.transition_to(LifecycleState.INITIALIZING)
    assert state.status == LifecycleState.INITIALIZING

    state.transition_to(LifecycleState.RUNNING)
    assert state.status == LifecycleState.RUNNING
    assert state.started_at is not None

    state.transition_to(LifecycleState.STOPPING)
    assert state.status == LifecycleState.STOPPING

    state.transition_to(LifecycleState.STOPPED)
    assert state.status == LifecycleState.STOPPED
    assert state.stopped_at is not None


def test_invalid_transition_stopped_to_running():
    """Verify that a STOPPED runtime cannot directly transition back to RUNNING."""
    state = RuntimeState()
    state.transition_to(LifecycleState.INITIALIZING)
    state.transition_to(LifecycleState.RUNNING)
    state.transition_to(LifecycleState.STOPPING)
    state.transition_to(LifecycleState.STOPPED)

    with pytest.raises(InvalidStateTransitionError) as exc_info:
        state.transition_to(LifecycleState.RUNNING)

    assert exc_info.value.current_state == LifecycleState.STOPPED
    assert exc_info.value.target_state == LifecycleState.RUNNING


def test_invalid_transition_created_to_running():
    """Verify that CREATED cannot jump directly to RUNNING without INITIALIZING."""
    state = RuntimeState()
    with pytest.raises(InvalidStateTransitionError):
        state.transition_to(LifecycleState.RUNNING)


def test_error_transition_and_resolution():
    """Verify transition to ERROR state with error message recording."""
    state = RuntimeState()
    state.transition_to(LifecycleState.ERROR, error_detail="Startup component failure")
    assert state.status == LifecycleState.ERROR
    assert state.error_detail == "Startup component failure"

    # From ERROR can transition to STOPPED
    state.transition_to(LifecycleState.STOPPED)
    assert state.status == LifecycleState.STOPPED
