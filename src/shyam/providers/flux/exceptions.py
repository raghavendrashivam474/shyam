"""Flux Provider Exceptions (S7).

Boundary-specific errors for the Shyam ↔ Flux Gateway contract.
"""

from __future__ import annotations

from typing import Any


class FluxClientError(Exception):
    """Base error for Flux Gateway communication."""

    def __init__(
        self,
        message: str,
        code: str | None = None,
        http_status: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.detail = detail or {}


class FluxConnectionError(FluxClientError):
    """Cannot reach the Flux Gateway."""

    def __init__(self, message: str = "Flux Gateway is unreachable") -> None:
        super().__init__(message, code="connection_failed")


class FluxProtocolError(FluxClientError):
    """Incompatible protocol version."""

    def __init__(self, message: str = "Incompatible Flux protocol") -> None:
        super().__init__(message, code="protocol_mismatch")


class FluxPeerNotFoundError(FluxClientError):
    """Requested peer is not known to Flux."""

    def __init__(self, peer_id: str) -> None:
        super().__init__(
            f"Peer not found: {peer_id}",
            code="peer_not_found",
            http_status=404,
        )


class FluxTransferError(FluxClientError):
    """Transfer operation failed."""

    def __init__(self, message: str, transfer_id: str | None = None) -> None:
        super().__init__(message, code="transfer_failed")
        self.transfer_id = transfer_id


class FluxUnavailableError(FluxClientError):
    """Flux node is not in a usable state."""

    def __init__(self, message: str = "Flux is unavailable") -> None:
        super().__init__(message, code="unavailable", http_status=503)
