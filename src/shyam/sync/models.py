"""Peer Synchronization domain models — S14.

Defines the explicit wire-level contract for state exchange between
trusted Shyam nodes. These models are deliberately decoupled from
S12 EcosystemState internals: S14 synchronizes *facts*, not entire
runtime snapshots.

Architectural boundaries:
    - S12 owns local ecosystem state truth.
    - S13 owns identity, keys, and trust.
    - S14 owns *what* gets synchronized and *how* it converges.
    - Flux owns *how bytes travel between nodes*.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------

SYNC_PROTOCOL_VERSION = "1.0"
"""Bump this when the wire format changes incompatibly."""


# ---------------------------------------------------------------------------
# Version metadata
# ---------------------------------------------------------------------------

class NodeVersionMap(BaseModel):
    """Per-node version vector.

    Maps node_id (str) → monotonic local version (int).
    This is NOT a global clock. Each node maintains its own counter.
    The map lets peers reason about "I've seen node X through version N."

    Example::

        {
            "node-A-uuid": 17,
            "node-B-uuid": 4,
            "node-C-uuid": 9,
        }
    """

    model_config = ConfigDict(frozen=True)

    versions: dict[str, int] = Field(
        default_factory=dict,
        description="Mapping of node_id to last-known local version.",
    )

    def get_version(self, node_id: str) -> int:
        """Return the version for a specific node, or 0 if unseen."""
        return self.versions.get(node_id, 0)

    def with_update(self, node_id: str, version: int) -> NodeVersionMap:
        """Return a new map with one node's version updated (immutable)."""
        updated = dict(self.versions)
        updated[node_id] = version
        return NodeVersionMap(versions=updated)


# ---------------------------------------------------------------------------
# Synchronization payload
# ---------------------------------------------------------------------------

class SyncPayload(BaseModel):
    """The actual state facts being exchanged.

    Deliberately structured, not a raw EcosystemState dump.
    Only replicable, non-sensitive facts belong here.

    Local-only state (private keys, credentials, workflow internals,
    Zarya execution state) must NEVER appear in this payload.
    """

    model_config = ConfigDict(frozen=True)

    # Discovery observations (from S8, safe to share)
    known_node_ids: list[str] = Field(
        default_factory=list,
        description="Node IDs this peer has observed.",
    )
    node_capabilities: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Mapping of node_id → list of capability_ids observed.",
    )
    node_availability: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of node_id → availability status string.",
    )

    # Extensible metadata for future S15/S16 needs
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Forward-compatible metadata. Consumers must ignore unknown keys.",
    )


# ---------------------------------------------------------------------------
# Wire envelope
# ---------------------------------------------------------------------------

class SyncEnvelope(BaseModel):
    """Signed synchronization message exchanged between trusted peers.

    This is the top-level wire object. Every sync message — whether
    request, response, or advertisement — is wrapped in this envelope.

    Verification order (enforced by S14 authenticator):
        1. Parse envelope schema
        2. Check protocol_version compatibility
        3. Identify sender via sender_node_id
        4. Lookup trust record for sender
        5. Verify signature over canonical payload bytes
        6. Evaluate version/conflict semantics
        7. Apply state
    """

    model_config = ConfigDict(frozen=True)

    # -- sender identification --
    sender_node_id: str = Field(
        description="Logical node ID of the sender (string UUID).",
    )
    sender_public_key: str = Field(
        description="Base64-encoded Ed25519 public key of the sender.",
    )

    # -- protocol --
    protocol_version: str = Field(
        default=SYNC_PROTOCOL_VERSION,
        description="Wire format version for forward compatibility.",
    )
    message_type: str = Field(
        description="One of: 'sync_request', 'sync_response', 'state_advertisement'.",
    )

    # -- state metadata --
    version_map: NodeVersionMap = Field(
        description="Sender's view of per-node versions.",
    )

    # -- payload --
    payload: SyncPayload = Field(
        description="The state facts being communicated.",
    )

    # -- integrity --
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this envelope was created.",
    )
    message_id: str = Field(
        description="Unique ID for this message (idempotency/replay protection).",
    )
    signature: str = Field(
        default="",
        description="Base64-encoded Ed25519 signature over canonical bytes. Empty before signing.",
    )

    def is_signed(self) -> bool:
        """True if a signature has been applied."""
        return bool(self.signature)


# ---------------------------------------------------------------------------
# Sync result (local, not sent over wire)
# ---------------------------------------------------------------------------

class SyncOutcome(StrEnum):
    """Result classification after processing a sync message."""

    APPLIED = "applied"
    ALREADY_CURRENT = "already_current"
    REJECTED_UNTRUSTED = "rejected_untrusted"
    REJECTED_INVALID_SIGNATURE = "rejected_invalid_signature"
    REJECTED_PROTOCOL_MISMATCH = "rejected_protocol_mismatch"
    REJECTED_MALFORMED = "rejected_malformed"
    REJECTED_REVOKED = "rejected_revoked"
    CONFLICT = "conflict"
    ERROR = "error"


class SyncResult(BaseModel):
    """Local outcome of processing a single synchronization message.

    Not sent over the wire — used internally by SyncService and tests.
    """

    model_config = ConfigDict(frozen=True)

    outcome: SyncOutcome
    sender_node_id: str = ""
    message_id: str = ""
    local_version_before: int = 0
    local_version_after: int = 0
    detail: str = ""
