"""Unit tests for ZaryaProvider - S6."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from shyam.capabilities.model import AvailabilityStatus
from shyam.providers.zarya.client import ZaryaClient
from shyam.providers.zarya.exceptions import ZaryaConnectionError
from shyam.providers.zarya.models import (
    CapabilitiesResponse,
    CapabilityEntry,
    EcosystemStatus,
    IdentityResponse,
    ProtocolResponse,
    StatusResponse,
    VerificationOutcome,
    WorkExecuteResponse,
)
from shyam.providers.zarya.provider import ZaryaProvider


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock(spec=ZaryaClient)
    client.get_protocol.return_value = ProtocolResponse(
        current="eip-1.0",
        supported=["eip-1.0"],
    )
    client.get_identity.return_value = IdentityResponse(
        instance_id="zarya-inst-001",
        product="zarya",
        version="0.9.0",
        protocol="eip-1.0",
        platform="windows",
        architecture="AMD64",
    )
    client.get_capabilities.return_value = CapabilitiesResponse(
        protocol="eip-1.0",
        capabilities=[
            CapabilityEntry(id="system.health", version="1.0", description="Health"),
            CapabilityEntry(id="work.execute", version="1.0", description="Execute"),
        ],
        allowed_tools=["getWeather", "listFiles"],
    )
    client.get_status.return_value = StatusResponse(
        status=EcosystemStatus.READY,
        active_operations=0,
    )
    return client


def test_zarya_provider_initial_state() -> None:
    provider = ZaryaProvider()
    assert not provider.is_connected
    assert provider.descriptor.availability == AvailabilityStatus.UNAVAILABLE
    assert provider.capability_definitions == ()


def test_zarya_provider_connect_success(mock_client: MagicMock) -> None:
    provider = ZaryaProvider(client=mock_client)
    connected = provider.connect()

    assert connected is True
    assert provider.is_connected is True
    assert provider.descriptor.provider_id == "zarya.agent"
    assert provider.descriptor.availability == AvailabilityStatus.AVAILABLE
    assert len(provider.capability_definitions) == 2
    assert provider.capability_definitions[0].capability_id == "zarya.system.health"


def test_zarya_provider_connect_incompatible_protocol(mock_client: MagicMock) -> None:
    mock_client.get_protocol.return_value = ProtocolResponse(
        current="eip-2.0",
        supported=["eip-2.0"],
    )
    provider = ZaryaProvider(client=mock_client)
    connected = provider.connect()

    assert connected is False
    assert provider.is_connected is False
    assert provider.descriptor.availability == AvailabilityStatus.UNAVAILABLE


def test_zarya_provider_connect_connection_failure(mock_client: MagicMock) -> None:
    mock_client.get_protocol.side_effect = ZaryaConnectionError("Offline")
    provider = ZaryaProvider(client=mock_client)
    connected = provider.connect()

    assert connected is False
    assert provider.is_connected is False


def test_zarya_provider_execute_delegation(mock_client: MagicMock) -> None:
    mock_client.execute_work.return_value = WorkExecuteResponse(
        tool="getWeather",
        outcome=VerificationOutcome.VERIFIED_SUCCESS,
        verified=True,
        result={"temp": "25C"},
        summary="Done",
    )
    provider = ZaryaProvider(client=mock_client)
    provider.connect()

    resp = provider.execute("getWeather", {"city": "London"})
    assert resp.outcome == VerificationOutcome.VERIFIED_SUCCESS
    assert resp.verified is True
    mock_client.execute_work.assert_called_once_with("getWeather", {"city": "London"})


def test_zarya_provider_execute_when_disconnected_raises() -> None:
    provider = ZaryaProvider()
    with pytest.raises(ZaryaConnectionError):
        provider.execute("getWeather")


def test_zarya_provider_refresh_status(mock_client: MagicMock) -> None:
    provider = ZaryaProvider(client=mock_client)
    provider.connect()

    # Change status to BUSY
    mock_client.get_status.return_value = StatusResponse(
        status=EcosystemStatus.BUSY,
        active_operations=1,
    )
    new_avail = provider.refresh_status()
    assert new_avail == AvailabilityStatus.AVAILABLE
