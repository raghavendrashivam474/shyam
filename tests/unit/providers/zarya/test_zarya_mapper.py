"""Unit tests for Zarya to Shyam Mapper - S6."""

from __future__ import annotations

from shyam.capabilities.model import AvailabilityStatus
from shyam.providers.zarya.mapper import (
    PROVIDER_ID_ZARYA,
    map_capabilities_response,
    map_ecosystem_status_to_availability,
    map_to_shyam_provider,
)
from shyam.providers.zarya.models import (
    CapabilitiesResponse,
    CapabilityEntry,
    DeviceInfo,
    EcosystemStatus,
    IdentityResponse,
    StatusResponse,
)


def test_map_ecosystem_status() -> None:
    m = map_ecosystem_status_to_availability
    assert m(EcosystemStatus.READY) == AvailabilityStatus.AVAILABLE
    assert m(EcosystemStatus.BUSY) == AvailabilityStatus.AVAILABLE
    assert m(EcosystemStatus.STARTING) == AvailabilityStatus.REGISTERED
    assert m(EcosystemStatus.STOPPING) == AvailabilityStatus.UNAVAILABLE
    assert m(EcosystemStatus.UNAVAILABLE) == AvailabilityStatus.UNAVAILABLE


def test_map_capabilities_response() -> None:
    response = CapabilitiesResponse(
        protocol="eip-1.0",
        capabilities=[
            CapabilityEntry(
                id="system.health",
                version="1.0",
                description="Instance health",
                operations=["check"],
            ),
            CapabilityEntry(
                id="work.execute",
                version="1.0",
                description="Work execution",
                operations=["execute"],
            ),
        ],
        allowed_tools=["getWeather", "openWebsite"],
    )

    caps = map_capabilities_response(response)
    assert len(caps) == 2
    assert caps[0].capability_id == "zarya.system.health"
    assert caps[1].capability_id == "zarya.work.execute"
    assert caps[1].metadata["allowed_tools"] == [
        "getWeather",
        "openWebsite",
    ]


def test_map_to_shyam_provider() -> None:
    ident = IdentityResponse(
        instance_id="abcd-1234-efgh",
        product="zarya",
        version="0.9.0",
        protocol="eip-1.0",
        platform="windows",
        architecture="AMD64",
        device=DeviceInfo(
            device_id="dev-1",
            display_name="Desktop",
            device_type="desktop",
            platform="windows",
        ),
    )
    caps_resp = CapabilitiesResponse(
        protocol="eip-1.0",
        capabilities=[
            CapabilityEntry(id="system.health", version="1.0"),
            CapabilityEntry(id="work.execute", version="1.0"),
        ],
        allowed_tools=["getWeather"],
    )
    status_resp = StatusResponse(
        status=EcosystemStatus.READY,
        active_operations=0,
    )

    provider = map_to_shyam_provider(ident, caps_resp, status_resp)
    assert provider.provider_id == PROVIDER_ID_ZARYA
    assert provider.version == "0.9.0"
    assert provider.availability == AvailabilityStatus.AVAILABLE
    assert "zarya.system.health" in provider.capabilities
    assert "zarya.work.execute" in provider.capabilities
    assert provider.metadata["instance_id"] == "abcd-1234-efgh"
    assert provider.metadata["device"]["device_id"] == "dev-1"
