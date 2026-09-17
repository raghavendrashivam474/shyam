"""Runtime lifecycle states and transition logic for Shyam."""

from enum import StrEnum


class LifecycleState(StrEnum):
    """Enumeration of Shyam runtime lifecycle states."""

    CREATED = "CREATED"
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


# Strict allowable transitions map
VALID_TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.CREATED: {LifecycleState.INITIALIZING, LifecycleState.ERROR},
    LifecycleState.INITIALIZING: {
        LifecycleState.RUNNING,
        LifecycleState.ERROR,
        LifecycleState.STOPPING,
    },
    LifecycleState.RUNNING: {LifecycleState.STOPPING, LifecycleState.ERROR},
    LifecycleState.STOPPING: {LifecycleState.STOPPED, LifecycleState.ERROR},
    LifecycleState.STOPPED: set(),  # Terminal state: cannot transition directly
    LifecycleState.ERROR: {
        LifecycleState.STOPPED
    },  # Can only move to stopped upon error resolution/cleanup
}


class InvalidStateTransitionError(RuntimeError):
    """Raised when an illegal lifecycle state transition is attempted."""

    def __init__(self, current_state: LifecycleState, target_state: LifecycleState) -> None:
        super().__init__(
            f"Illegal lifecycle state transition attempted: "
            f"{current_state.value} -> {target_state.value}"
        )
        self.current_state = current_state
        self.target_state = target_state


def validate_transition(current: LifecycleState, target: LifecycleState) -> None:
    """Validate whether transitioning from current to target is allowed.

    Raises:
        InvalidStateTransitionError: If the transition is not allowed.
    """
    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStateTransitionError(current, target)
