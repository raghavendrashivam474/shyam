"""Unit tests for Zarya EIP-1 Protocol Models - S6."""

from __future__ import annotations

from shyam.providers.zarya.models import (
    AuthInfoResponse,
    CapabilitiesResponse,
    EcosystemErrorCode,
    EcosystemErrorEnvelope,
    EcosystemStatus,
    IdentityResponse,
    ProtocolResponse,
    VerificationOutcome,
    WorkExecuteRequest,
    WorkExecuteResponse,
)


def test_ecosystem_status_values() -> None:
    assert EcosystemStatus.READY.value == "READY"
    assert EcosystemStatus.BUSY.value == "BUSY"
    assert EcosystemStatus.STARTING.value == "STARTING"
    assert EcosystemStatus.STOPPING.value == "STOPPING"
    assert EcosystemStatus.UNAVAILABLE.value == "UNAVAILABLE"


def test_verification_outcome_values() -> None:
    assert VerificationOutcome.VERIFIED_SUCCESS.value == "VERIFIED_SUCCESS"
    assert VerificationOutcome.VERIFIED_FAILURE.value == "VERIFIED_FAILURE"
    assert VerificationOutcome.UNKNOWN.value == "UNKNOWN"


def test_auth_info_model() -> None:
    data = {
        "method": "header",
        "header_name": "X-Ecosystem-Token",
        "description": "Include the ecosystem token",
    }
    model = AuthInfoResponse.model_validate(data)
    assert model.method == "header"
    assert model.header_name == "X-Ecosystem-Token"


def test_identity_model_with_device() -> None:
    data = {
        "instance_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "product": "zarya",
        "version": "0.9.0",
        "protocol": "eip-1.0",
        "platform": "windows",
        "architecture": "AMD64",
        "device": {
            "device_id": "local-device-001",
            "display_name": "Raghav's Laptop",
            "device_type": "laptop",
            "platform": "windows",
        },
    }
    ident = IdentityResponse.model_validate(data)
    assert ident.product == "zarya"
    assert ident.device is not None
    assert ident.device.device_id == "local-device-001"


def test_identity_model_without_device() -> None:
    data = {
        "instance_id": "a1b2c3d4",
        "product": "zarya",
        "version": "0.9.0",
        "protocol": "eip-1.0",
        "platform": "windows",
        "architecture": "AMD64",
    }
    ident = IdentityResponse.model_validate(data)
    assert ident.device is None


def test_protocol_model() -> None:
    data = {"current": "eip-1.0", "supported": ["eip-1.0", "eip-1.1"]}
    proto = ProtocolResponse.model_validate(data)
    assert proto.current == "eip-1.0"
    assert "eip-1.0" in proto.supported


def test_capabilities_model() -> None:
    data = {
        "protocol": "eip-1.0",
        "capabilities": [
            {
                "id": "work.execute",
                "version": "1.0",
                "description": "Execute tool",
                "operations": ["execute"],
                "input_schema": {"tool": "string"},
                "output_schema": {"result": "object"},
            }
        ],
        "allowed_tools": ["getWeather", "listFiles"],
    }
    caps = CapabilitiesResponse.model_validate(data)
    assert len(caps.capabilities) == 1
    assert caps.capabilities[0].id == "work.execute"
    assert "getWeather" in caps.allowed_tools


def test_work_execute_models() -> None:
    req = WorkExecuteRequest(tool="getWeather", args={"city": "Chennai"})
    assert req.tool == "getWeather"
    assert req.args["city"] == "Chennai"

    resp_data = {
        "tool": "getWeather",
        "outcome": "VERIFIED_SUCCESS",
        "verified": True,
        "result": {"temp": "32C"},
        "summary": "Completed",
    }
    resp = WorkExecuteResponse.model_validate(resp_data)
    assert resp.outcome == VerificationOutcome.VERIFIED_SUCCESS
    assert resp.verified is True
    assert resp.result["temp"] == "32C"


def test_error_envelope_model() -> None:
    envelope_data = {
        "error": {
            "code": "TOOL_NOT_ALLOWED",
            "message": "Tool 'runTerminalCommand' is not permitted.",
            "detail": {"allowed_tools": ["getWeather"]},
        }
    }
    env = EcosystemErrorEnvelope.model_validate(envelope_data)
    assert env.error.code == EcosystemErrorCode.TOOL_NOT_ALLOWED
    assert "runTerminalCommand" in env.error.message
    assert env.error.detail["allowed_tools"] == ["getWeather"]
