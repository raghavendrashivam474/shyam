"""Exception hierarchy for S15 Bootstrap & Recovery."""

from __future__ import annotations


class BootstrapError(Exception):
    """Base exception for all bootstrap and recovery failures."""


class BootstrapRejectedError(BootstrapError):
    """Raised when a bootstrap request is explicitly rejected.

    Common causes:
        - Node identity is revoked in the trust store.
        - Cryptographic signature verification failed.
        - Bootstrap authority denied enrollment.
    """

    def __init__(self, node_id: str, reason: str) -> None:
        self.node_id = node_id
        self.reason = reason
        super().__init__(f"Bootstrap rejected for node '{node_id}': {reason}")


class BootstrapTimeoutError(BootstrapError):
    """Raised when a bootstrap session exceeds its allowed duration."""

    def __init__(self, session_id: str, timeout_seconds: float) -> None:
        self.session_id = session_id
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Bootstrap session '{session_id}' timed out after {timeout_seconds}s"
        )


class RecoveryError(BootstrapError):
    """Raised when a recovery operation fails."""