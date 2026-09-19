"""Flux Gateway API v1 — Contract Models (S7).

These models define the expected JSON shapes from the Flux Gateway HTTP API.
They represent the cross-process contract between Shyam and Flux, not Flux's
internal Rust types.

Contract spec: ADR-007
Flux Gateway base: http://127.0.0.1:9100/flux/v1
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ── Enums ────────────────────────────────────────────────────────


class FluxNodeState(StrEnum):
    """Flux node lifecycle states."""

    INITIALIZING = "initializing"
    RUNNING = "running"
    LISTENING = "listening"
    DEGRADED = "degraded"
    STOPPED = "stopped"


class FluxPathState(StrEnum):
    """Individual path health states."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    STALE = "stale"


class FluxTransportKind(StrEnum):
    """Transport type for a path."""

    TCP_LAN = "tcp_lan"
    TCP_WIFI = "tcp_wifi"
    TCP_DIRECT = "tcp_direct"
    RELAY = "relay"
    BLUETOOTH = "bluetooth"


class FluxTransferStatus(StrEnum):
    """Transfer lifecycle states."""

    QUEUED = "queued"
    CONNECTING = "connecting"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


# ── Identity ─────────────────────────────────────────────────────


class FluxIdentityResponse(BaseModel):
    """GET /flux/v1/identity"""

    peer_id: str = Field(..., description="UUID-v4 Flux PeerId")
    version: str = Field(..., description="Flux semantic version")
    protocol_version: str = Field(..., description="Wire protocol version")


# ── Status ───────────────────────────────────────────────────────


class FluxStatusResponse(BaseModel):
    """GET /flux/v1/status"""

    state: FluxNodeState
    peer_id: str
    discovered_peer_count: int = Field(default=0)
    active_path_count: int = Field(default=0)
    active_transfer_count: int = Field(default=0)


# ── Peers ────────────────────────────────────────────────────────


class FluxPathInfo(BaseModel):
    """Single path to a peer."""

    path_id: str
    transport: FluxTransportKind
    remote_addr: str
    state: FluxPathState
    rtt_ms: float | None = None
    last_seen: str | None = None


class FluxPeerInfo(BaseModel):
    """GET /flux/v1/peers/{peer_id}"""

    peer_id: str
    address: str | None = None
    last_seen: str | None = None
    paths: list[FluxPathInfo] = Field(default_factory=list)
    connectivity: str = Field(
        default="unknown",
        description="Overall connectivity: reachable | unreachable | unknown",
    )


class FluxPeersResponse(BaseModel):
    """GET /flux/v1/peers"""

    peers: list[FluxPeerInfo] = Field(default_factory=list)


# ── Connect ──────────────────────────────────────────────────────


class FluxConnectRequest(BaseModel):
    """POST /flux/v1/connect"""

    peer_id: str


class FluxConnectResponse(BaseModel):
    """POST /flux/v1/connect response"""

    peer_id: str
    connected: bool
    active_path_count: int = Field(default=0)


# ── Transfer ─────────────────────────────────────────────────────


class FluxTransferRequest(BaseModel):
    """POST /flux/v1/transfer"""

    peer_id: str
    artifact_path: str = Field(..., description="Local path to artifact")
    artifact_name: str | None = None
    is_directory: bool = False


class FluxTransferResponse(BaseModel):
    """POST /flux/v1/transfer response"""

    transfer_id: str
    peer_id: str
    status: FluxTransferStatus


class FluxTransferStatusResponse(BaseModel):
    """GET /flux/v1/transfer/{transfer_id}"""

    transfer_id: str
    peer_id: str
    status: FluxTransferStatus
    progress_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    bytes_transferred: int = Field(default=0)
    bytes_total: int = Field(default=0)
    error_message: str | None = None


class FluxCancelResponse(BaseModel):
    """POST /flux/v1/transfer/{transfer_id}/cancel"""

    transfer_id: str
    status: FluxTransferStatus


# ── Error ────────────────────────────────────────────────────────


class FluxErrorDetail(BaseModel):
    """Structured error from Flux Gateway."""

    code: str
    message: str
    detail: dict[str, Any] | None = None
