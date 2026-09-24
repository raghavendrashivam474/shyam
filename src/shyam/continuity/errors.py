"""S16 Continuity error types.

Explicit error hierarchy for continuity coordination failures.
These are distinct from Zarya execution errors and Flux transfer errors.
"""

from __future__ import annotations


class ContinuityError(Exception):
    """Base error for all S16 continuity operations."""

    def __init__(self, continuity_id: str, reason: str) -> None:
        self.continuity_id = continuity_id
        self.reason = reason
        super().__init__(f"[{continuity_id}] {reason}")


class InvalidContinuityTransitionError(ContinuityError):
    """Raised when a lifecycle state transition is not permitted."""

    def __init__(
        self,
        continuity_id: str,
        current: str,
        attempted: str,
    ) -> None:
        self.current = current
        self.attempted = attempted
        super().__init__(
            continuity_id,
            f"Invalid transition: {current} -> {attempted}",
        )


class TargetIneligibleError(ContinuityError):
    """Raised when the selected target cannot satisfy continuity requirements."""

    def __init__(self, continuity_id: str, target_node_id: str, reason: str) -> None:
        self.target_node_id = target_node_id
        super().__init__(continuity_id, f"Target '{target_node_id}' ineligible: {reason}")


class ArtifactTransferError(ContinuityError):
    """Raised when Flux artifact transfer fails during continuity."""

    def __init__(
        self,
        continuity_id: str,
        transfer_id: str | None,
        reason: str,
    ) -> None:
        self.transfer_id = transfer_id
        super().__init__(continuity_id, f"Artifact transfer failed: {reason}")


class ContinuationRejectedError(ContinuityError):
    """Raised when target Zarya N4 rejects the continuation request."""

    def __init__(self, continuity_id: str, reason: str) -> None:
        super().__init__(continuity_id, f"Continuation rejected by target: {reason}")


class DuplicateContinuityError(ContinuityError):
    """Raised when an idempotency violation is detected."""

    def __init__(self, continuity_id: str, work_id: str) -> None:
        self.work_id = work_id
        super().__init__(
            continuity_id,
            f"Duplicate continuity for work '{work_id}'",
        )
