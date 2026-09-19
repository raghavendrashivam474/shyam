"""Unit tests for Flux Gateway contract models and exceptions."""

from shyam.providers.flux.exceptions import (
    FluxClientError,
    FluxConnectionError,
    FluxPeerNotFoundError,
    FluxProtocolError,
    FluxTransferError,
    FluxUnavailableError,
)
from shyam.providers.flux.models import (
    FluxIdentityResponse,
    FluxNodeState,
    FluxPathState,
    FluxPeerInfo,
    FluxPeersResponse,
    FluxStatusResponse,
    FluxTransferRequest,
    FluxTransferResponse,
    FluxTransferStatus,
    FluxTransferStatusResponse,
    FluxTransportKind,
)


def test_flux_identity_model() -> None:
    data = {
        "peer_id": "550e8400-e29b-41d4-a716-446655440000",
        "version": "2.3.0",
        "protocol_version": "1.0",
    }
    identity = FluxIdentityResponse.model_validate(data)
    assert identity.peer_id == "550e8400-e29b-41d4-a716-446655440000"
    assert identity.version == "2.3.0"
    assert identity.protocol_version == "1.0"


def test_flux_status_model() -> None:
    data = {
        "state": "running",
        "peer_id": "550e8400-e29b-41d4-a716-446655440000",
        "discovered_peer_count": 3,
        "active_path_count": 5,
        "active_transfer_count": 1,
    }
    status = FluxStatusResponse.model_validate(data)
    assert status.state == FluxNodeState.RUNNING
    assert status.discovered_peer_count == 3
    assert status.active_path_count == 5


def test_flux_peers_model() -> None:
    peer_data = {
        "peer_id": "peer-123",
        "address": "192.168.1.50:9000",
        "connectivity": "reachable",
        "paths": [
            {
                "path_id": "path-1",
                "transport": "tcp_lan",
                "remote_addr": "192.168.1.50:9000",
                "state": "available",
                "rtt_ms": 1.2,
            }
        ],
    }
    peer = FluxPeerInfo.model_validate(peer_data)
    assert peer.peer_id == "peer-123"
    assert len(peer.paths) == 1
    assert peer.paths[0].transport == FluxTransportKind.TCP_LAN
    assert peer.paths[0].state == FluxPathState.AVAILABLE
    assert peer.paths[0].rtt_ms == 1.2

    resp = FluxPeersResponse.model_validate({"peers": [peer_data]})
    assert len(resp.peers) == 1


def test_flux_transfer_models() -> None:
    req = FluxTransferRequest(
        peer_id="peer-123",
        artifact_path="/tmp/test.bin",
        artifact_name="test.bin",
    )
    assert req.peer_id == "peer-123"
    assert not req.is_directory

    resp = FluxTransferResponse(
        transfer_id="xfer-001",
        peer_id="peer-123",
        status=FluxTransferStatus.QUEUED,
    )
    assert resp.status == FluxTransferStatus.QUEUED

    status_resp = FluxTransferStatusResponse(
        transfer_id="xfer-001",
        peer_id="peer-123",
        status=FluxTransferStatus.IN_PROGRESS,
        progress_percent=45.5,
        bytes_transferred=4550,
        bytes_total=10000,
    )
    assert status_resp.progress_percent == 45.5


def test_flux_exceptions_hierarchy() -> None:
    err = FluxClientError("Custom error", code="custom_code", http_status=400)
    assert isinstance(err, Exception)
    assert err.code == "custom_code"
    assert err.http_status == 400

    conn_err = FluxConnectionError()
    assert isinstance(conn_err, FluxClientError)

    proto_err = FluxProtocolError("mismatch")
    assert isinstance(proto_err, FluxClientError)

    peer_err = FluxPeerNotFoundError("peer-xyz")
    assert peer_err.http_status == 404
    assert "peer-xyz" in str(peer_err)

    xfer_err = FluxTransferError("disk full", transfer_id="t1")
    assert xfer_err.transfer_id == "t1"

    unavail_err = FluxUnavailableError()
    assert unavail_err.http_status == 503
