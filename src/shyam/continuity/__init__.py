"""S16 Cross-Device Work Continuity subsystem.

Coordinates work continuation across trusted Shyam nodes by
orchestrating S9 (navigation), S13 (trust), Flux (transfer),
and Zarya N4 (continuation).
"""

from shyam.continuity.errors import (
    ArtifactTransferError,
    ContinuationRejectedError,
    ContinuityError,
    DuplicateContinuityError,
    InvalidContinuityTransitionError,
    TargetIneligibleError,
)
from shyam.continuity.models import (
    ContinuityOutcome,
    ContinuityRequest,
    ContinuityResult,
    ContinuitySession,
    ContinuityTarget,
)
from shyam.continuity.service import ContinuityService
from shyam.continuity.state import (
    ContinuityState,
    is_terminal,
    is_valid_transition,
)

__all__ = [
    "ArtifactTransferError",
    "ContinuationRejectedError",
    "ContinuityError",
    "ContinuityOutcome",
    "ContinuityRequest",
    "ContinuityResult",
    "ContinuityService",
    "ContinuitySession",
    "ContinuityState",
    "ContinuityTarget",
    "DuplicateContinuityError",
    "InvalidContinuityTransitionError",
    "TargetIneligibleError",
    "is_terminal",
    "is_valid_transition",
]