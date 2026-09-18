"""Zarya EIP-1 Provider Exceptions - S6.

Maps EIP-1 structured errors to Python exceptions while preserving
the original error code and semantics. These do NOT replace Shyam's
existing provider exceptions — they live inside the Zarya layer.
"""

from __future__ import annotations

from shyam.providers.zarya.models import EcosystemErrorCode


class ZaryaClientError(Exception):
    """Base exception for all Zarya EIP-1 client errors."""

    def __init__(
        self,
        message: str,
        *,
        code: EcosystemErrorCode | None = None,
        http_status: int | None = None,
        detail: dict | None = None,
    ) -> None:
        self.code = code
        self.http_status = http_status
        self.detail = detail or {}
        super().__init__(message)


class ZaryaConnectionError(ZaryaClientError):
    """Zarya instance is unreachable (network/process down)."""


class ZaryaAuthenticationError(ZaryaClientError):
    """Missing, invalid, or expired ecosystem token."""

    def __init__(self, message: str = "Invalid or missing ecosystem token") -> None:
        super().__init__(
            message,
            code=EcosystemErrorCode.UNAUTHORIZED,
            http_status=401,
        )


class ZaryaProtocolError(ZaryaClientError):
    """Protocol version mismatch or incompatible response."""


class ZaryaToolNotAllowedError(ZaryaClientError):
    """Attempted to invoke a tool not in the allowed_tools list."""

    def __init__(
        self,
        tool: str,
        allowed_tools: list[str] | None = None,
    ) -> None:
        self.tool = tool
        self.allowed_tools = allowed_tools or []
        super().__init__(
            f"Tool '{tool}' is not permitted through the ecosystem boundary.",
            code=EcosystemErrorCode.TOOL_NOT_ALLOWED,
            http_status=403,
            detail={"allowed_tools": self.allowed_tools},
        )


class ZaryaVerificationError(ZaryaClientError):
    """Operation completed but verification outcome was not VERIFIED_SUCCESS."""

    def __init__(self, tool: str, outcome: str, summary: str = "") -> None:
        self.tool = tool
        self.outcome = outcome
        self.summary = summary
        super().__init__(
            f"Verification failed for '{tool}': {outcome}. {summary}",
            code=EcosystemErrorCode.VERIFICATION_FAILED,
        )


class ZaryaBusyError(ZaryaClientError):
    """Zarya is currently BUSY and cannot accept work."""

    def __init__(self, message: str = "Zarya is busy") -> None:
        super().__init__(
            message,
            code=EcosystemErrorCode.BUSY,
            http_status=503,
        )


class ZaryaUnavailableError(ZaryaClientError):
    """Zarya is UNAVAILABLE."""

    def __init__(self, message: str = "Zarya is unavailable") -> None:
        super().__init__(
            message,
            code=EcosystemErrorCode.UNAVAILABLE,
            http_status=503,
        )
