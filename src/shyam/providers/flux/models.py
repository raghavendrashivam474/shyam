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
    """Transfer lifecycle states matching Gateway TransferStatus.

    Gateway uses #[serde(rename_all = "SCREAMING_SNAKE_CASE")]:
    CREATED, RUNNING, COMPLETED, FAILED, CANCELLED
    """
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


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
    """GET /flux/v1/peers/{peer_id} — matches Gateway PeerSummary."""

    peer_id: str
    address: str | None = None
    last_seen: str | None = None
    last_seen_secs_ago: float | None = None
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
    """POST /flux/v1/connect response — matches Gateway ConnectResponse."""

    peer_id: str
    success: bool = True
    connected_address: str | None = None
    message: str | None = None
    connected: bool | None = None
    active_path_count: int = Field(default=0)

    @property
    def is_connected(self) -> bool:
        return self.connected if self.connected is not None else self.success


# ── Transfer ─────────────────────────────────────────────────────


class FluxTransferRequest(BaseModel):
    """POST /flux/v1/transfer — matches Gateway StartTransferRequest."""
    peer_id: str
    file_paths: list[str] = Field(..., description="List of local file paths to transfer")


class FluxTransferResponse(BaseModel):
    """POST /flux/v1/transfer response — matches Gateway StartTransferResponse.

    Note: The POST response does NOT include peer_id.
    Use GET /transfer/{id} (FluxTransferStatusResponse) for peer_id.
    """
    transfer_id: str
    status: FluxTransferStatus


class FluxTransferStatusResponse(BaseModel):
    """GET /flux/v1/transfer/{transfer_id} — matches Gateway GatewayTransferInfo."""
    transfer_id: str
    peer_id: str
    status: FluxTransferStatus
    bytes_transferred: int = Field(default=0)
    total_bytes: int = Field(default=0)
    files_transferred: int = Field(default=0)
    total_files: int = Field(default=0)
    error_message: str | None = None


class FluxCancelResponse(BaseModel):
    """POST /flux/v1/transfer/{transfer_id}/cancel — matches Gateway CancelTransferResponse."""
    transfer_id: str
    cancelled: bool


# ── Error ────────────────────────────────────────────────────────


class FluxErrorDetail(BaseModel):
    """Structured error from Flux Gateway."""

    code: str
    message: str
    detail: dict[str, Any] | None = None
