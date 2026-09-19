"""Unit tests for FluxClient."""

import io
import json
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from shyam.providers.flux.client import FluxClient
from shyam.providers.flux.exceptions import (
    FluxConnectionError,
    FluxPeerNotFoundError,
    FluxProtocolError,
    FluxTransferError,
    FluxUnavailableError,
)
from shyam.providers.flux.models import FluxNodeState, FluxTransferStatus


def _mock_http_response(status: int = 200, json_data: dict | None = None) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status = status
    body = json.dumps(json_data or {}).encode("utf-8")
    mock_resp.read.return_value = body
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


def test_get_identity_success() -> None:
    client = FluxClient()
    payload = {
        "peer_id": "flux-peer-1",
        "version": "2.3.0",
        "protocol_version": "1.0",
    }
    with patch("urllib.request.urlopen", return_value=_mock_http_response(200, payload)):
        resp = client.get_identity()
        assert resp.peer_id == "flux-peer-1"
        assert resp.version == "2.3.0"


def test_get_status_success() -> None:
    client = FluxClient()
    payload = {
        "state": "running",
        "peer_id": "flux-peer-1",
        "discovered_peer_count": 2,
        "active_path_count": 3,
        "active_transfer_count": 0,
    }
    with patch("urllib.request.urlopen", return_value=_mock_http_response(200, payload)):
        resp = client.get_status()
        assert resp.state == FluxNodeState.RUNNING
        assert resp.active_path_count == 3


def test_get_peers_and_peer_detail() -> None:
    client = FluxClient()
    peers_payload = {
        "peers": [
            {
                "peer_id": "peer-abc",
                "connectivity": "reachable",
                "paths": [],
            }
        ]
    }
    with patch("urllib.request.urlopen", return_value=_mock_http_response(200, peers_payload)):
        peers_resp = client.get_peers()
        assert len(peers_resp.peers) == 1
        assert peers_resp.peers[0].peer_id == "peer-abc"

    peer_detail = {
        "peer_id": "peer-abc",
        "address": "10.0.0.2:9000",
        "connectivity": "reachable",
        "paths": [
            {
                "path_id": "p-1",
                "transport": "tcp_lan",
                "remote_addr": "10.0.0.2:9000",
                "state": "available",
            }
        ],
    }
    with patch("urllib.request.urlopen", return_value=_mock_http_response(200, peer_detail)):
        detail_resp = client.get_peer("peer-abc")
        assert detail_resp.peer_id == "peer-abc"
        assert len(detail_resp.paths) == 1


def test_transfer_lifecycle() -> None:
    client = FluxClient()

    # 1. Connect
    payload_conn = {"peer_id": "p1", "connected": True, "active_path_count": 2}
    with patch(
        "urllib.request.urlopen",
        return_value=_mock_http_response(200, payload_conn),
    ):
        conn_resp = client.connect_peer("p1")
        assert conn_resp.connected is True

    # 2. Initiate Transfer
    payload_init = {"transfer_id": "t100", "peer_id": "p1", "status": "queued"}
    with patch(
        "urllib.request.urlopen",
        return_value=_mock_http_response(200, payload_init),
    ):
        xfer_resp = client.initiate_transfer(peer_id="p1", artifact_path="/tmp/file.txt")
        assert xfer_resp.transfer_id == "t100"
        assert xfer_resp.status == FluxTransferStatus.QUEUED

    # 3. Status
    payload_status = {
        "transfer_id": "t100",
        "peer_id": "p1",
        "status": "in_progress",
        "progress_percent": 50.0,
        "bytes_transferred": 50,
        "bytes_total": 100,
    }
    with patch(
        "urllib.request.urlopen",
        return_value=_mock_http_response(200, payload_status),
    ):
        status_resp = client.get_transfer_status("t100")
        assert status_resp.progress_percent == 50.0

    # 4. Cancel
    payload_cancel = {"transfer_id": "t100", "status": "cancelled"}
    with patch(
        "urllib.request.urlopen",
        return_value=_mock_http_response(200, payload_cancel),
    ):
        cancel_resp = client.cancel_transfer("t100")
        assert cancel_resp.status == FluxTransferStatus.CANCELLED


def test_client_connection_error() -> None:
    client = FluxClient()
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        with pytest.raises(FluxConnectionError) as exc_info:
            client.get_identity()
        assert "Cannot reach Flux Gateway" in str(exc_info.value)


def test_client_structured_http_errors() -> None:
    client = FluxClient()

    # 404 Peer Not Found
    err_body = json.dumps(
        {"code": "peer_not_found", "message": "Peer missing", "detail": {"peer_id": "px"}}
    ).encode()
    http_404 = urllib.error.HTTPError(
        "http://127.0.0.1", 404, "Not Found", {}, io.BytesIO(err_body)
    )
    with patch("urllib.request.urlopen", side_effect=http_404):
        with pytest.raises(FluxPeerNotFoundError):
            client.get_peer("px")

    # 409 Protocol Error
    err_body = json.dumps(
        {"code": "protocol_mismatch", "message": "Unsupported wire protocol"}
    ).encode()
    http_409 = urllib.error.HTTPError(
        "http://127.0.0.1", 409, "Conflict", {}, io.BytesIO(err_body)
    )
    with patch("urllib.request.urlopen", side_effect=http_409):
        with pytest.raises(FluxProtocolError):
            client.get_identity()

    # 503 Unavailable Error
    err_body = json.dumps({"code": "unavailable", "message": "Flux shutting down"}).encode()
    http_503 = urllib.error.HTTPError(
        "http://127.0.0.1", 503, "Unavailable", {}, io.BytesIO(err_body)
    )
    with patch("urllib.request.urlopen", side_effect=http_503):
        with pytest.raises(FluxUnavailableError):
            client.get_status()

    # Generic Transfer Error
    err_body = json.dumps(
        {"code": "transfer_rejected", "message": "Disk capacity exceeded"}
    ).encode()
    http_500 = urllib.error.HTTPError(
        "http://127.0.0.1", 500, "Server Error", {}, io.BytesIO(err_body)
    )
    with patch("urllib.request.urlopen", side_effect=http_500):
        with pytest.raises(FluxTransferError):
            client.initiate_transfer("p1", "/tmp/large.iso")
