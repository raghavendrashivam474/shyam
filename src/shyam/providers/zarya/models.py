"""EIP-1 Protocol Data Models - S6.

Pydantic models matching the frozen Zarya EIP-1 specification
(zarya-ecosystem / eip-1.0). These represent the wire format,
not Shyam's internal domain objects.

Source of truth: Zarya docs/architecture/eip1-protocol-specification.md
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ── Enums ────────────────────────────────────────────────────


class EcosystemStatus(StrEnum):
    """Zarya ecosystem-level availability states."""

    READY = "READY"
    BUSY = "BUSY"
    STARTING = "STARTING"
    STOPPING = "STOPPING"
    UNAVAILABLE = "UNAVAILABLE"


class VerificationOutcome(StrEnum):
    """Zarya S2 verification outcomes.

    HTTP 200 does NOT automatically mean success.
    The outcome field carries the real verification result.
    """

    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    VERIFIED_FAILURE = "VERIFIED_FAILURE"
    UNKNOWN = "UNKNOWN"


class EcosystemErrorCode(StrEnum):
    """Structured error codes from the EIP-1 error model."""

    INVALID_REQUEST = "INVALID_REQUEST"
    UNSUPPORTED_PROTOCOL = "UNSUPPORTED_PROTOCOL"
    CAPABILITY_NOT_ADVERTISED = "CAPABILITY_NOT_ADVERTISED"
    OPERATION_NOT_SUPPORTED = "OPERATION_NOT_SUPPORTED"
    UNAUTHORIZED = "UNAUTHORIZED"
    BUSY = "BUSY"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID_STATE = "INVALID_STATE"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    TOOL_NOT_ALLOWED = "TOOL_NOT_ALLOWED"
    UNKNOWN = "UNKNOWN"


# ── Discovery Responses ──────────────────────────────────────


class AuthInfoResponse(BaseModel):
    """GET /ecosystem/v1/auth-info (unauthenticated)."""

    method: str
    header_name: str
    description: str = ""


class DeviceInfo(BaseModel):
    """Nested device projection inside identity."""

    device_id: str
    display_name: str
    device_type: str
    platform: str


class IdentityResponse(BaseModel):
    """GET /ecosystem/v1/identity."""

    instance_id: str
    product: str
    version: str
    protocol: str
    platform: str
    architecture: str
    device: DeviceInfo | None = None


class ProtocolResponse(BaseModel):
    """GET /ecosystem/v1/protocol."""

    current: str
    supported: list[str]


class CapabilityEntry(BaseModel):
    """Single capability inside the capabilities response."""

    id: str
    version: str
    description: str = ""
    operations: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None


class CapabilitiesResponse(BaseModel):
    """GET /ecosystem/v1/capabilities."""

    protocol: str
    capabilities: list[CapabilityEntry] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)


class StatusResponse(BaseModel):
    """GET /ecosystem/v1/status."""

    status: EcosystemStatus
    active_operations: int = 0


# ── Operational Models ───────────────────────────────────────


class WorkExecuteRequest(BaseModel):
    """POST /ecosystem/v1/work/execute request body."""

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class WorkExecuteResponse(BaseModel):
    """POST /ecosystem/v1/work/execute response body."""

    tool: str
    outcome: VerificationOutcome
    verified: bool
    result: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""


class WorkStatusDetail(BaseModel):
    """Nested detail inside work status response."""

    status: str = ""
    total_steps: int = 0
    completed_steps: int = 0


class WorkStatusResponse(BaseModel):
    """GET /ecosystem/v1/work/status/{operation_id}."""

    operation_id: str
    ecosystem_status: str = ""
    lifecycle_status: str = ""
    detail: WorkStatusDetail | None = None


# ── Error Model ──────────────────────────────────────────────


class EcosystemErrorDetail(BaseModel):
    """Inner error object inside the FastAPI detail envelope."""

    code: EcosystemErrorCode
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class EcosystemErrorEnvelope(BaseModel):
    """Top-level error wrapper matching FastAPI's detail envelope.

    Structure: {"detail": {"error": {"code": ..., "message": ...}}}
    """

    error: EcosystemErrorDetail
