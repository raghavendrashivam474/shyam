"""Unit tests for S16 domain models and state transitions."""

import pytest
from pydantic import ValidationError

from shyam.continuity.models import (
    ContinuityOutcome,
    ContinuityRequest,
    ContinuityResult,
    ContinuitySession,
    ContinuityTarget,
)
from shyam.continuity.state import (
    ContinuityState,
    is_terminal,
    is_valid_transition,
)
from shyam.navigation.models import NavigationConstraints


def test_continuity_state_transitions() -> None:
    """Verify validity of key lifecycle state transitions."""
    # Happy path transitions
    assert is_valid_transition(ContinuityState.REQUESTED, ContinuityState.VALIDATING)
    assert is_valid_transition(ContinuityState.VALIDATING, ContinuityState.TARGET_SELECTED)
    assert is_valid_transition(ContinuityState.TARGET_SELECTED, ContinuityState.AUTHORIZED)
    assert is_valid_transition(ContinuityState.AUTHORIZED, ContinuityState.PREPARING)
    assert is_valid_transition(ContinuityState.PREPARING, ContinuityState.TRANSFERRING)
    assert is_valid_transition(ContinuityState.TRANSFERRING, ContinuityState.RECONSTRUCTING)
    assert is_valid_transition(ContinuityState.RECONSTRUCTING, ContinuityState.CONTINUING)
    assert is_valid_transition(ContinuityState.CONTINUING, ContinuityState.VERIFYING)
    assert is_valid_transition(ContinuityState.VERIFYING, ContinuityState.COMPLETED)

    # Alternate terminal routes
    assert is_valid_transition(ContinuityState.REQUESTED, ContinuityState.FAILED)
    assert is_valid_transition(ContinuityState.REQUESTED, ContinuityState.CANCELLED)
    assert is_valid_transition(ContinuityState.REQUESTED, ContinuityState.UNSUPPORTED)
    assert is_valid_transition(ContinuityState.VERIFYING, ContinuityState.UNKNOWN)

    # Invalid transitions
    assert not is_valid_transition(ContinuityState.COMPLETED, ContinuityState.REQUESTED)
    assert not is_valid_transition(ContinuityState.FAILED, ContinuityState.VALIDATING)
    assert not is_valid_transition(ContinuityState.TRANSFERRING, ContinuityState.REQUESTED)


def test_continuity_state_terminal() -> None:
    """Verify terminal state designations."""
    assert is_terminal(ContinuityState.COMPLETED)
    assert is_terminal(ContinuityState.FAILED)
    assert is_terminal(ContinuityState.CANCELLED)
    assert is_terminal(ContinuityState.UNSUPPORTED)
    assert is_terminal(ContinuityState.UNKNOWN)

    assert not is_terminal(ContinuityState.REQUESTED)
    assert not is_terminal(ContinuityState.TRANSFERRING)
    assert not is_terminal(ContinuityState.VERIFYING)


def test_continuity_request_validation() -> None:
    """Verify ContinuityRequest validations and defaults."""
    req = ContinuityRequest(
        work_id="W-123",
        source_device_id="dev-source",
        portable_work={"type": "file_work", "data": "payload"},
    )
    assert req.work_id == "W-123"
    assert req.continuity_intent == "COPY"
    assert req.artifact_paths == ()
    assert isinstance(req.target_constraints, NavigationConstraints)

    # Test lowercase intent conversion
    req2 = ContinuityRequest(
        work_id="W-123",
        source_device_id="dev-source",
        portable_work={"type": "file_work"},
        continuity_intent="handoff",
    )
    assert req2.continuity_intent == "HANDOFF"

    # Test validation failures
    with pytest.raises(ValidationError):
        ContinuityRequest(
            work_id="  ",  # empty work_id
            source_device_id="dev-source",
            portable_work={"type": "file_work"},
        )

    with pytest.raises(ValidationError):
        ContinuityRequest(
            work_id="W-123",
            source_device_id="dev-source",
            portable_work={"type": "file_work"},
            continuity_intent="INVALID_INTENT",
        )


def test_identity_isolation() -> None:
    """Ensure strict identity separation inside ContinuitySession."""
    req = ContinuityRequest(
        work_id="W-999",
        source_device_id="dev-source",
        portable_work={"type": "generic"},
    )
    session = ContinuitySession(request=req)

    # All distinct IDs
    assert session.continuity_id != req.work_id
    assert session.transfer_id is None
    assert session.operation_id is None