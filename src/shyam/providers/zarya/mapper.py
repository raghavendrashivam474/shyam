"""Zarya to Shyam Translation / Mapping Layer - S6.

Converts Zarya EIP-1 wire models into Shyam domain models:
- IdentityResponse -> Provider metadata
- CapabilityEntry / allowed_tools -> Capability
- EcosystemStatus -> AvailabilityStatus
"""

from __future__ import annotations

import logging
from typing import Any

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.providers.model import Provider
from shyam.providers.zarya.models import (
    CapabilitiesResponse,
    CapabilityEntry,
    EcosystemStatus,
    IdentityResponse,
    StatusResponse,
)

logger = logging.getLogger(__name__)

EXPECTED_PROTOCOL = "eip-1.0"
PROVIDER_ID_ZARYA = "zarya.agent"


def map_ecosystem_status_to_availability(status: EcosystemStatus) -> AvailabilityStatus:
    """Map Zarya EcosystemStatus to Shyam AvailabilityStatus.

    Mapping:
        READY       -> AVAILABLE
        BUSY        -> AVAILABLE
        STARTING    -> REGISTERED
        STOPPING    -> UNAVAILABLE
        UNAVAILABLE -> UNAVAILABLE
    """
    mapping = {
        EcosystemStatus.READY: AvailabilityStatus.AVAILABLE,
        EcosystemStatus.BUSY: AvailabilityStatus.AVAILABLE,
        EcosystemStatus.STARTING: AvailabilityStatus.REGISTERED,
        EcosystemStatus.STOPPING: AvailabilityStatus.UNAVAILABLE,
        EcosystemStatus.UNAVAILABLE: AvailabilityStatus.UNAVAILABLE,
    }
    return mapping.get(status, AvailabilityStatus.UNAVAILABLE)


def map_capability_entry_to_capability(
    entry: CapabilityEntry,
    allowed_tools: list[str] | None = None,
) -> Capability:
    """Map a single Zarya CapabilityEntry to a Shyam Capability object.

    Capability ID format: zarya.<capability_id>
    """
    cap_id = f"zarya.{entry.id}"
    human_name = f"Zarya {entry.id.replace('.', ' ').title()}"

    metadata: dict[str, Any] = {
        "source": "zarya-eip1",
        "operations": entry.operations,
        "input_schema": entry.input_schema,
        "output_schema": entry.output_schema,
    }

    if entry.id == "work.execute" and allowed_tools is not None:
        metadata["allowed_tools"] = allowed_tools

    return Capability(
        capability_id=cap_id,
        name=human_name,
        version=entry.version,
        description=entry.description,
        availability=AvailabilityStatus.AVAILABLE,
        metadata=metadata,
    )


def map_capabilities_response(
    response: CapabilitiesResponse,
) -> list[Capability]:
    """Map full CapabilitiesResponse into a list of Shyam Capability objects."""
    caps: list[Capability] = []
    for entry in response.capabilities:
        caps.append(
            map_capability_entry_to_capability(
                entry,
                allowed_tools=response.allowed_tools,
            )
        )
    return caps


def map_to_shyam_provider(
    identity: IdentityResponse,
    capabilities_resp: CapabilitiesResponse,
    status_resp: StatusResponse,
) -> Provider:
    """Translate Zarya discovery responses into a frozen Shyam Provider descriptor.

    Preserves Zarya's sovereign identity, protocol version, and advertised capabilities
    without modifying or replacing Shyam's NodeIdentity.
    """
    capability_ids = tuple(f"zarya.{c.id}" for c in capabilities_resp.capabilities)
    availability = map_ecosystem_status_to_availability(status_resp.status)

    metadata: dict[str, Any] = {
        "product": identity.product,
        "instance_id": identity.instance_id,
        "protocol": identity.protocol,
        "platform": identity.platform,
        "architecture": identity.architecture,
        "allowed_tools": capabilities_resp.allowed_tools,
    }

    if identity.device:
        metadata["device"] = identity.device.model_dump()

    return Provider(
        provider_id=PROVIDER_ID_ZARYA,
        name=f"Zarya ({identity.platform})",
        version=identity.version,
        description=f"Zarya sovereign agent [{identity.instance_id[:8]}]",
        capabilities=capability_ids,
        availability=availability,
        metadata=metadata,
    )
