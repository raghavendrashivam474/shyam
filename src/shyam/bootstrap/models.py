"""Domain models for S15 Device Bootstrap & Recovery.

These models represent the bootstrap and recovery lifecycles.
S15 coordinates S13 (identity, trust), S14 (sync), and S8 (discovery)
without replacing any of them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class BootstrapState(StrEnum):
    """S15 bootstrap lifecycle state machine."""

    UNINITIALIZED = "uninitialized"
    IDENTITY_READY = "identity_ready"
    BOOTSTRAP_REQUESTED = "bootstrap_requested"
    AUTHENTICATING = "authenticating"
    TRUST_ESTABLISHED = "trust_established"
    STATE_INITIALIZING = "state_initializing"
    SYNCING = "syncing"
    READY = "ready"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


_VALID_TRANSITIONS: dict[BootstrapState, frozenset[BootstrapState]] = {
    BootstrapState.UNINITIALIZED: frozenset({BootstrapState.IDENTITY_READY}),
    BootstrapState.IDENTITY_READY: frozenset({BootstrapState.BOOTSTRAP_REQUESTED}),
    BootstrapState.BOOTSTRAP_REQUESTED: frozenset({BootstrapState.AUTHENTICATING}),
    BootstrapState.AUTHENTICATING: frozenset({
        BootstrapState.TRUST_ESTABLISHED,
        BootstrapState.REJECTED,
        BootstrapState.FAILED,
        BootstrapState.CANCELLED,
    }),
    BootstrapState.TRUST_ESTABLISHED: frozenset({
        BootstrapState.STATE_INITIALIZING,
        BootstrapState.FAILED,
        BootstrapState.CANCELLED,
    }),
    BootstrapState.STATE_INITIALIZING: frozenset({
        BootstrapState.SYNCING,
        BootstrapState.FAILED,
        BootstrapState.CANCELLED,
    }),
    BootstrapState.SYNCING: frozenset({
        BootstrapState.READY,
        BootstrapState.FAILED,
        BootstrapState.CANCELLED,
    }),
    BootstrapState.READY: frozenset(),
    BootstrapState.FAILED: frozenset(),
    BootstrapState.REJECTED: frozenset(),
    BootstrapState.CANCELLED: frozenset(),
}


class BootstrapOutcome(StrEnum):
    """Terminal outcome classification for a bootstrap attempt."""

    SUCCESS = "success"
    REJECTED_REVOKED = "rejected_revoked"
    REJECTED_UNTRUSTED = "rejected_untrusted"
    REJECTED_INVALID_IDENTITY = "rejected_invalid_identity"
    REJECTED_SIGNATURE = "rejected_signature"
    FAILED_TIMEOUT = "failed_timeout"
    FAILED_SYNC = "failed_sync"
    FAILED_INTERNAL = "failed_internal"
    CANCELLED = "cancelled"


class BootstrapRequest(BaseModel):
    """Enrollment request sent by a new or recovering device."""

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this bootstrap request.",
    )
    node_id: str = Field(
        description="Logical node ID (string UUID) of the requesting device.",
    )
    public_key: str = Field(
        description="Base64-encoded Ed25519 public key of the requesting device.",
    )
    node_name: str = Field(
        default="",
        description="Human-readable display name of the requesting device.",
    )
    protocol_version: str = Field(
        default="0.2.0",
        description="Shyam protocol version of the requesting device.",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when this request was created.",
    )
    signature: str = Field(
        default="",
        description="Base64 Ed25519 signature over request fields.",
    )
    is_recovery: bool = Field(
        default=False,
        description="True if this is a recovery attempt rather than fresh enrollment.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Forward-compatible metadata.",
    )


class BootstrapResponse(BaseModel):
    """Response from the bootstrap authority to the requesting device."""

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(
        description="Matches the original BootstrapRequest.request_id.",
    )
    accepted: bool = Field(
        description="Whether the bootstrap request was accepted.",
    )
    authority_node_id: str = Field(
        default="",
        description="Node ID of the bootstrap authority.",
    )
    authority_public_key: str = Field(
        default="",
        description="Public key of the bootstrap authority.",
    )
    rejection_reason: str = Field(
        default="",
        description="Human-readable reason if rejected.",
    )
    outcome: BootstrapOutcome = Field(
        default=BootstrapOutcome.SUCCESS,
        description="Terminal outcome classification.",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )


class BootstrapSession(BaseModel):
    """Local tracking of a bootstrap lifecycle on the joining device."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(
        default_factory=lambda: str(uuid4()),
    )
    state: BootstrapState = Field(
        default=BootstrapState.UNINITIALIZED,
    )
    node_id: str = Field(
        default="",
        description="Local node ID once identity is established.",
    )
    authority_node_id: str = Field(
        default="",
        description="Node ID of the bootstrap authority.",
    )
    outcome: BootstrapOutcome | None = Field(
        default=None,
    )
    error_detail: str = Field(
        default="",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )

    def transition(self, new_state: BootstrapState) -> BootstrapSession:
        """Advance state per the validated lifecycle state machine."""
        allowed = _VALID_TRANSITIONS.get(self.state, frozenset())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid bootstrap transition: {self.state.value} -> {new_state.value}. "
                f"Allowed: {[s.value for s in allowed]}"
            )
        return self.model_copy(update={
            "state": new_state,
            "updated_at": datetime.now(UTC),
        })

    @property
    def is_terminal(self) -> bool:
        return self.state in (
            BootstrapState.READY,
            BootstrapState.FAILED,
            BootstrapState.REJECTED,
            BootstrapState.CANCELLED,
        )

    @property
    def is_successful(self) -> bool:
        return self.state == BootstrapState.READY


class RecoveryScenario(StrEnum):
    """Classification of the device recovery situation."""

    STATE_LOST_IDENTITY_INTACT = "state_lost_identity_intact"
    IDENTITY_LOST = "identity_lost"
    PARTIAL_STATE = "partial_state"
    INTERRUPTED_BOOTSTRAP = "interrupted_bootstrap"
    REVOKED_NODE = "revoked_node"
    UNKNOWN = "unknown"


class RecoveryRequest(BaseModel):
    """Initiates a recovery process for a previously known device."""

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(
        default_factory=lambda: str(uuid4()),
    )
    scenario: RecoveryScenario = Field(
        default=RecoveryScenario.UNKNOWN,
    )
    existing_node_id: str = Field(
        default="",
    )
    public_key: str = Field(
        default="",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )


class RecoveryResult(BaseModel):
    """Outcome of a recovery attempt."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    success: bool
    scenario: RecoveryScenario
    new_node_id: str = Field(
        default="",
    )
    detail: str = Field(
        default="",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )