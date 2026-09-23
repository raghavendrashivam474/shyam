"""Unit tests for S15 Bootstrap & Recovery domain models and state machine."""

import pytest
from uuid import uuid4

from shyam.bootstrap.errors import (
    BootstrapError,
    BootstrapRejectedError,
    BootstrapTimeoutError,
    RecoveryError,
)
from shyam.bootstrap.models import (
    BootstrapOutcome,
    BootstrapRequest,
    BootstrapResponse,
    BootstrapSession,
    BootstrapState,
    RecoveryRequest,
    RecoveryResult,
    RecoveryScenario,
)


class TestBootstrapStateMachine:
    """Test lifecycle states, valid progressions, and transition guards."""

    def test_initial_session_state(self) -> None:
        session = BootstrapSession()
        assert session.state == BootstrapState.UNINITIALIZED
        assert not session.is_terminal
        assert not session.is_successful

    def test_full_successful_lifecycle(self) -> None:
        s0 = BootstrapSession()
        s1 = s0.transition(BootstrapState.IDENTITY_READY)
        assert s1.state == BootstrapState.IDENTITY_READY

        s2 = s1.transition(BootstrapState.BOOTSTRAP_REQUESTED)
        assert s2.state == BootstrapState.BOOTSTRAP_REQUESTED

        s3 = s2.transition(BootstrapState.AUTHENTICATING)
        assert s3.state == BootstrapState.AUTHENTICATING

        s4 = s3.transition(BootstrapState.TRUST_ESTABLISHED)
        assert s4.state == BootstrapState.TRUST_ESTABLISHED

        s5 = s4.transition(BootstrapState.STATE_INITIALIZING)
        assert s5.state == BootstrapState.STATE_INITIALIZING

        s6 = s5.transition(BootstrapState.SYNCING)
        assert s6.state == BootstrapState.SYNCING

        s7 = s6.transition(BootstrapState.READY)
        assert s7.state == BootstrapState.READY
        assert s7.is_terminal
        assert s7.is_successful

    def test_invalid_transitions_raise(self) -> None:
        session = BootstrapSession()
        # Cannot jump from UNINITIALIZED directly to READY or SYNCING
        with pytest.raises(ValueError, match="Invalid bootstrap transition"):
            session.transition(BootstrapState.READY)

        with pytest.raises(ValueError, match="Invalid bootstrap transition"):
            session.transition(BootstrapState.SYNCING)

    def test_terminal_states_have_no_transitions(self) -> None:
        session = BootstrapSession(state=BootstrapState.READY)
        assert session.is_terminal
        with pytest.raises(ValueError, match="Invalid bootstrap transition"):
            session.transition(BootstrapState.IDENTITY_READY)

        rejected = BootstrapSession(state=BootstrapState.REJECTED)
        assert rejected.is_terminal
        with pytest.raises(ValueError, match="Invalid bootstrap transition"):
            rejected.transition(BootstrapState.AUTHENTICATING)

    def test_rejection_path(self) -> None:
        session = (
            BootstrapSession()
            .transition(BootstrapState.IDENTITY_READY)
            .transition(BootstrapState.BOOTSTRAP_REQUESTED)
            .transition(BootstrapState.AUTHENTICATING)
            .transition(BootstrapState.REJECTED)
        )
        assert session.state == BootstrapState.REJECTED
        assert session.is_terminal
        assert not session.is_successful


class TestBootstrapModels:
    """Test payload schemas and immutability."""

    def test_bootstrap_request_creation_and_immutability(self) -> None:
        node_id = str(uuid4())
        req = BootstrapRequest(
            node_id=node_id,
            public_key="b64key",
            node_name="test-laptop",
        )
        assert req.node_id == node_id
        assert req.public_key == "b64key"
        assert req.protocol_version == "0.2.0"
        assert req.request_id is not None

        # Frozen immutability
        with pytest.raises(Exception):
            req.node_id = "new-id"  # type: ignore

    def test_bootstrap_response_model(self) -> None:
        resp = BootstrapResponse(
            request_id="req-123",
            accepted=True,
            authority_node_id="auth-node-1",
            authority_public_key="auth-pub-key",
            outcome=BootstrapOutcome.SUCCESS,
        )
        assert resp.accepted
        assert resp.authority_node_id == "auth-node-1"

    def test_recovery_request_and_result(self) -> None:
        rec_req = RecoveryRequest(
            scenario=RecoveryScenario.STATE_LOST_IDENTITY_INTACT,
            existing_node_id="existing-1",
        )
        assert rec_req.scenario == RecoveryScenario.STATE_LOST_IDENTITY_INTACT

        rec_res = RecoveryResult(
            request_id=rec_req.request_id,
            success=True,
            scenario=rec_req.scenario,
            new_node_id="existing-1",
            detail="Restored",
        )
        assert rec_res.success
        assert rec_res.new_node_id == "existing-1"


class TestBootstrapExceptions:
    """Test exception hierarchy and string formatting."""

    def test_bootstrap_rejected_error(self) -> None:
        err = BootstrapRejectedError("node-1", "revoked node identity")
        assert "node-1" in str(err)
        assert "revoked node identity" in str(err)
        assert isinstance(err, BootstrapError)

    def test_bootstrap_timeout_error(self) -> None:
        err = BootstrapTimeoutError("sess-1", 15.0)
        assert "sess-1" in str(err)
        assert "15.0s" in str(err)
        assert isinstance(err, BootstrapError)

    def test_recovery_error(self) -> None:
        err = RecoveryError("sync failure during recovery")
        assert isinstance(err, BootstrapError)