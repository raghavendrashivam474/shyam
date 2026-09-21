"""Trust domain models and events for Shyam — S13.

Represents local trust policies, trust relationships, and verification states.
Trust decisions are local to each Shyam node and are decoupled from S8 discovery facts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from shyam.events.bus import Event


class TrustStatus(StrEnum):
    """Explicit trust status assigned to a remote node or identity."""

    UNKNOWN = "unknown"
    TRUSTED = "trusted"
    REVOKED = "revoked"


class RelationshipType(StrEnum):
    """Categorization of trust relationship."""

    NONE = "none"
    PERSONAL = "personal"
    PEER = "peer"
    INFRASTRUCTURE = "infrastructure"


class TrustRecord(BaseModel):
    """Immutable local record of trust for an ecosystem identity."""

    model_config = ConfigDict(frozen=True)

    node_id: str = Field(
        description="Logical node ID (string representation of UUID or peer ID).",
    )
    public_key: str | None = Field(
        default=None,
        description="Base64-encoded public key if known/pinned.",
    )
    status: TrustStatus = Field(
        default=TrustStatus.UNKNOWN,
        description="Current trust standing of this node.",
    )
    relationship: RelationshipType = Field(
        default=RelationshipType.NONE,
        description="Type of relationship established with this node.",
    )
    alias: str = Field(
        default="",
        description="Human-friendly label/alias for this node.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this trust record was first created.",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this trust record was last modified.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional policy or provenance metadata.",
    )

    @property
    def is_trusted(self) -> bool:
        """Convenience property: True if status is TRUSTED."""
        return self.status == TrustStatus.TRUSTED

    @property
    def is_revoked(self) -> bool:
        """Convenience property: True if status is REVOKED."""
        return self.status == TrustStatus.REVOKED

    def with_status(
        self,
        status: TrustStatus,
        relationship: RelationshipType | None = None,
        alias: str | None = None,
        public_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TrustRecord:
        """Return an updated copy with new trust state and updated timestamp."""
        updates: dict[str, Any] = {
            "status": status,
            "updated_at": datetime.now(UTC),
        }
        if relationship is not None:
            updates["relationship"] = relationship
        if alias is not None:
            updates["alias"] = alias
        if public_key is not None:
            updates["public_key"] = public_key
        if metadata is not None:
            updates["metadata"] = metadata
        return self.model_copy(update=updates)


# ---------------------------------------------------------------------------
# Trust Events
# ---------------------------------------------------------------------------


class TrustGrantedEvent(Event):
    """Emitted when trust is granted to a node identity."""

    node_id: str
    public_key: str | None = None
    relationship: RelationshipType = RelationshipType.PERSONAL
    alias: str = ""


class TrustRevokedEvent(Event):
    """Emitted when trust is revoked from a node identity."""

    node_id: str
    reason: str | None = None


class TrustUpdatedEvent(Event):
    """Emitted when a trust record's metadata, key, or relationship is updated."""

    node_id: str
    status: TrustStatus
    relationship: RelationshipType
