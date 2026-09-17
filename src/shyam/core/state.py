"""Runtime state tracking models for Shyam."""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from shyam.core.lifecycle import LifecycleState, validate_transition


class RuntimeState(BaseModel):
    """Encapsulates the immediate runtime state of a Shyam node."""

    runtime_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this runtime instance execution.",
    )
    status: LifecycleState = Field(
        default=LifecycleState.CREATED,
        description="Current lifecycle state of the runtime.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when runtime was instantiated.",
    )
    started_at: datetime | None = Field(
        default=None,
        description="Timestamp when runtime reached RUNNING state.",
    )
    stopped_at: datetime | None = Field(
        default=None,
        description="Timestamp when runtime reached STOPPED state.",
    )
    error_detail: str | None = Field(
        default=None,
        description="Error message if runtime encountered an ERROR state.",
    )

    def transition_to(self, next_state: LifecycleState, error_detail: str | None = None) -> None:
        """Transition the runtime state to a new lifecycle phase."""
        validate_transition(self.status, next_state)
        self.status = next_state

        now = datetime.now(UTC)
        if next_state == LifecycleState.RUNNING:
            self.started_at = now
        elif next_state == LifecycleState.STOPPED:
            self.stopped_at = now
        elif next_state == LifecycleState.ERROR:
            self.error_detail = error_detail
