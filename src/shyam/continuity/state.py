"""S16 Continuity lifecycle state machine.

Follows the same pattern as S15 BootstrapState: explicit StrEnum
with a frozen transition map. No implicit transitions.
"""

from __future__ import annotations

from enum import StrEnum


class ContinuityState(StrEnum):
    """S16 continuity lifecycle states."""

    REQUESTED = "requested"
    VALIDATING = "validating"
    TARGET_SELECTED = "target_selected"
    AUTHORIZED = "authorized"
    PREPARING = "preparing"
    TRANSFERRING = "transferring"
    RECONSTRUCTING = "reconstructing"
    CONTINUING = "continuing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


# Terminal states — no outgoing transitions allowed.
TERMINAL_STATES: frozenset[ContinuityState] = frozenset({
    ContinuityState.COMPLETED,
    ContinuityState.FAILED,
    ContinuityState.CANCELLED,
    ContinuityState.UNSUPPORTED,
    ContinuityState.UNKNOWN,
})

# Explicit transition map.
# Every non-terminal state must declare its valid successors.
_VALID_TRANSITIONS: dict[ContinuityState, frozenset[ContinuityState]] = {
    ContinuityState.REQUESTED: frozenset({
        ContinuityState.VALIDATING,
        ContinuityState.FAILED,
        ContinuityState.CANCELLED,
        ContinuityState.UNSUPPORTED,
    }),
    ContinuityState.VALIDATING: frozenset({
        ContinuityState.TARGET_SELECTED,
        ContinuityState.FAILED,
        ContinuityState.CANCELLED,
        ContinuityState.UNSUPPORTED,
    }),
    ContinuityState.TARGET_SELECTED: frozenset({
        ContinuityState.AUTHORIZED,
        ContinuityState.FAILED,
        ContinuityState.CANCELLED,
    }),
    ContinuityState.AUTHORIZED: frozenset({
        ContinuityState.PREPARING,
        ContinuityState.FAILED,
        ContinuityState.CANCELLED,
    }),
    ContinuityState.PREPARING: frozenset({
        ContinuityState.TRANSFERRING,
        ContinuityState.FAILED,
        ContinuityState.CANCELLED,
    }),
    ContinuityState.TRANSFERRING: frozenset({
        ContinuityState.RECONSTRUCTING,
        ContinuityState.FAILED,
        ContinuityState.CANCELLED,
    }),
    ContinuityState.RECONSTRUCTING: frozenset({
        ContinuityState.CONTINUING,
        ContinuityState.FAILED,
        ContinuityState.CANCELLED,
    }),
    ContinuityState.CONTINUING: frozenset({
        ContinuityState.VERIFYING,
        ContinuityState.FAILED,
        ContinuityState.CANCELLED,
    }),
    ContinuityState.VERIFYING: frozenset({
        ContinuityState.COMPLETED,
        ContinuityState.FAILED,
        ContinuityState.UNKNOWN,
    }),
    # Terminal states — no outgoing transitions.
    ContinuityState.COMPLETED: frozenset(),
    ContinuityState.FAILED: frozenset(),
    ContinuityState.CANCELLED: frozenset(),
    ContinuityState.UNSUPPORTED: frozenset(),
    ContinuityState.UNKNOWN: frozenset(),
}


def is_valid_transition(
    current: ContinuityState,
    target: ContinuityState,
) -> bool:
    """Check whether a state transition is permitted."""
    return target in _VALID_TRANSITIONS.get(current, frozenset())


def is_terminal(state: ContinuityState) -> bool:
    """Check whether a state is terminal (no further transitions)."""
    return state in TERMINAL_STATES
