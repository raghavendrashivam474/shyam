"""Node identity models for Shyam."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class NodeIdentity(BaseModel):
    """Immutable identity of a Shyam computing node."""

    model_config = ConfigDict(frozen=True)

    node_id: UUID = Field(
        default_factory=uuid4,
        description="Unique, persistent identifier of the Shyam node.",
    )
    node_name: str = Field(
        description="Human-readable display name for this node.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when this node identity was first generated.",
    )
    protocol_version: str = Field(
        default="0.2.0",
        description="Shyam node protocol compatibility version.",
    )
