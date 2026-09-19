"""Unit tests for ZaryaClient - S6."""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from shyam.providers.zarya.client import ZaryaClient
from shyam.providers.zarya.exceptions import (
    ZaryaAuthenticationError,
    ZaryaConnectionError,
    ZaryaToolNotAllowedError,
    ZaryaVerificationError,
)
from shyam.providers.zarya.models import (
    EcosystemStatus,
    VerificationOutcome,
)


def make_mock_response(status: int, body_dict: dict) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.read.return_value = json.dumps(body_dict).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


def test_client_missing_token_raises() -> None:
    client = ZaryaClient(token="")
    with pytest.raises(ZaryaAuthenticationError):
        client.get_identity()


@patch("urllib.request.urlopen")
def test_client_get_auth_info_no_token_required(
    mock_urlopen: MagicMock,
) -> None:
    mock_urlopen.return_value = make_mock_response(
        200,
        {
            "method": "header",
            "header_name": "X-Ecosystem-Token",
            "description": "Auth header",
        },
    )
    client = ZaryaClient(token="")
    info = client.get_auth_info()
    assert info.header_name == "X-Ecosystem-Token"


@patch("urllib.request.urlopen")
def test_client_get_identity(mock_urlopen: MagicMock) -> None:
    mock_urlopen.return_value = make_mock_response(
        200,
        {
            "instance_id": "inst-123",
            "product": "zarya",
            "version": "0.9.0",
            "protocol": "eip-1.0",
            "platform": "windows",
            "architecture": "AMD64",
        },
    )
    client = ZaryaClient(token="secret-token")
    ident = client.get_identity()
    assert ident.instance_id == "inst-123"
    assert ident.product == "zarya"


@patch("urllib.request.urlopen")
def test_client_get_capabilities(mock_urlopen: MagicMock) -> None:
    mock_urlopen.return_value = make_mock_response(
        200,
        {
            "protocol": "eip-1.0",
            "capabilities": [
                {
                    "id": "system.health",
                    "version": "1.0",
                    "description": "Health check",
                    "operations": ["check"],
                }
            ],
            "allowed_tools": ["getWeather"],
        },
    )
    client = ZaryaClient(token="secret-token")
    caps = client.get_capabilities()
    assert len(caps.capabilities) == 1
    assert caps.allowed_tools == ["getWeather"]


@patch("urllib.request.urlopen")
def test_client_get_status(mock_urlopen: MagicMock) -> None:
    mock_urlopen.return_value = make_mock_response(
        200,
        {"status": "READY", "active_operations": 0},
    )
    client = ZaryaClient(token="secret-token")
    status = client.get_status()
    assert status.status == EcosystemStatus.READY


@patch("urllib.request.urlopen")
def test_client_execute_work_success(mock_urlopen: MagicMock) -> None:
    mock_urlopen.return_value = make_mock_response(
        200,
        {
            "tool": "getWeather",
            "outcome": "VERIFIED_SUCCESS",
            "verified": True,
            "result": {"temp": "28C"},
            "summary": "Weather checked",
        },
    )
    client = ZaryaClient(token="secret-token")
    resp = client.execute_work("getWeather", {"city": "Paris"})
    assert resp.outcome == VerificationOutcome.VERIFIED_SUCCESS
    assert resp.verified is True
    assert resp.result["temp"] == "28C"


@patch("urllib.request.urlopen")
def test_client_execute_verification_failure(
    mock_urlopen: MagicMock,
) -> None:
    mock_urlopen.return_value = make_mock_response(
        200,
        {
            "tool": "listFiles",
            "outcome": "VERIFIED_FAILURE",
            "verified": False,
            "result": {},
            "summary": "Post-execution verification failed",
        },
    )
    client = ZaryaClient(token="secret-token")
    with pytest.raises(ZaryaVerificationError) as exc_info:
        client.execute_work("listFiles")
    assert "listFiles" in str(exc_info.value)
    assert "VERIFIED_FAILURE" in str(exc_info.value)


@patch("urllib.request.urlopen")
def test_client_tool_not_allowed_error(
    mock_urlopen: MagicMock,
) -> None:
    err_body = json.dumps(
        {
            "detail": {
                "error": {
                    "code": "TOOL_NOT_ALLOWED",
                    "message": (
                        "Tool 'runTerminalCommand' is not permitted through the ecosystem boundary."
                    ),
                    "detail": {
                        "allowed_tools": ["getWeather", "listFiles"],
                    },
                }
            }
        }
    ).encode("utf-8")

    err = urllib.error.HTTPError(
        url="http://127.0.0.1:8765/ecosystem/v1/work/execute",
        code=403,
        msg="Forbidden",
        hdrs={},  # type: ignore[arg-type]
        fp=io.BytesIO(err_body),
    )
    mock_urlopen.side_effect = err

    client = ZaryaClient(token="secret-token")
    with pytest.raises(ZaryaToolNotAllowedError) as exc_info:
        client.execute_work("runTerminalCommand")
    assert exc_info.value.tool == "runTerminalCommand"
    assert "getWeather" in exc_info.value.allowed_tools


@patch("urllib.request.urlopen")
def test_client_connection_error(mock_urlopen: MagicMock) -> None:
    mock_urlopen.side_effect = urllib.error.URLError(
        "Connection refused",
    )
    client = ZaryaClient(token="secret-token")
    with pytest.raises(ZaryaConnectionError):
        client.get_status()


@patch("urllib.request.urlopen")
def test_client_server_rejects_token_401(mock_urlopen: MagicMock) -> None:
    """Regression: server-side 401 with EIP-1 envelope raises ZaryaAuthenticationError."""
    error_body = json.dumps({
        "detail": {
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Invalid or expired ecosystem token.",
                "detail": {},
            }
        }
    }).encode("utf-8")
    http_401 = urllib.error.HTTPError(
        "http://127.0.0.1:8765/ecosystem/v1/identity",
        401,
        "Unauthorized",
        {"Content-Type": "application/json"},
        io.BytesIO(error_body),
    )
    mock_urlopen.side_effect = http_401
    client = ZaryaClient(token="stale-token")
    with pytest.raises(ZaryaAuthenticationError, match="Invalid or expired ecosystem token"):
        client.get_identity()