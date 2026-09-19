"""Discovery models and peer representations for Shyam."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shyam.events.bus import Event


class Peer(BaseModel):
    """Immutable representation of a discovered remote Shyam node."""

    model_config = ConfigDict(frozen=True)

    node_id: UUID = Field(
        description="Unique persistent identifier of the peer node.",
    )
    node_name: str = Field(
        description="Display name of the peer node.",
    )
    address: str = Field(
        description="Network IP address where the peer is reachable.",
    )
    port: int = Field(
        description="Port number where the peer is accepting communication.",
    )
    protocol_version: str = Field(
        default="0.2.0",
        description="Shyam protocol version used by the peer.",
    )
    discovered_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the peer was first discovered.",
    )
    last_seen: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the peer was most recently observed.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional transport or routing metadata announced by peer.",
    )

    def touch(self, seen_at: datetime | None = None) -> "Peer":
        """Return a copy of this peer with an updated last_seen timestamp."""
        return self.model_copy(update={"last_seen": seen_at or datetime.now(UTC)})


# --- Discovery Events ---


class NodeIdentityReadyEvent(Event):
    """Fired when this node's identity has been successfully initialized/loaded."""

    node_id: UUID
    node_name: str
    protocol_version: str


class PeerDiscoveredEvent(Event):
    """Fired when a new Shyam peer is discovered for the first time."""

    peer: Peer


class PeerUpdatedEvent(Event):
    """Fired when an existing peer's announced metadata or address changes."""

    peer: Peer


class PeerLostEvent(Event):
    """Fired when a previously known peer fails heartbeat and expires."""

    node_id: UUID
    node_name: str
    last_seen: datetime
