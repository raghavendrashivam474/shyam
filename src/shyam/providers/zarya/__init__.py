"""Zarya EIP-1 Provider Integration - S6.

Consumes the Zarya ecosystem contract (zarya-ecosystem / eip-1.0)
and exposes Zarya as a sovereign Shyam Provider.
"""

from shyam.providers.zarya.client import ZaryaClient as ZaryaClient
from shyam.providers.zarya.exceptions import (
    ZaryaAuthenticationError as ZaryaAuthenticationError,
)
from shyam.providers.zarya.exceptions import (
    ZaryaBusyError as ZaryaBusyError,
)
from shyam.providers.zarya.exceptions import (
    ZaryaClientError as ZaryaClientError,
)
from shyam.providers.zarya.exceptions import (
    ZaryaConnectionError as ZaryaConnectionError,
)
from shyam.providers.zarya.exceptions import (
    ZaryaProtocolError as ZaryaProtocolError,
)
from shyam.providers.zarya.exceptions import (
    ZaryaToolNotAllowedError as ZaryaToolNotAllowedError,
)
from shyam.providers.zarya.exceptions import (
    ZaryaUnavailableError as ZaryaUnavailableError,
)
from shyam.providers.zarya.exceptions import (
    ZaryaVerificationError as ZaryaVerificationError,
)
from shyam.providers.zarya.mapper import (
    EXPECTED_PROTOCOL as EXPECTED_PROTOCOL,
)
from shyam.providers.zarya.mapper import (
    PROVIDER_ID_ZARYA as PROVIDER_ID_ZARYA,
)
from shyam.providers.zarya.mapper import (
    map_capabilities_response as map_capabilities_response,
)
from shyam.providers.zarya.mapper import (
    map_ecosystem_status_to_availability as map_ecosystem_status_to_availability,
)
from shyam.providers.zarya.mapper import (
    map_to_shyam_provider as map_to_shyam_provider,
)
from shyam.providers.zarya.models import (
    AuthInfoResponse as AuthInfoResponse,
)
from shyam.providers.zarya.models import (
    CapabilitiesResponse as CapabilitiesResponse,
)
from shyam.providers.zarya.models import (
    CapabilityEntry as CapabilityEntry,
)
from shyam.providers.zarya.models import (
    EcosystemErrorCode as EcosystemErrorCode,
)
from shyam.providers.zarya.models import (
    EcosystemStatus as EcosystemStatus,
)
from shyam.providers.zarya.models import (
    IdentityResponse as IdentityResponse,
)
from shyam.providers.zarya.models import (
    ProtocolResponse as ProtocolResponse,
)
from shyam.providers.zarya.models import (
    StatusResponse as StatusResponse,
)
from shyam.providers.zarya.models import (
    VerificationOutcome as VerificationOutcome,
)
from shyam.providers.zarya.models import (
    WorkExecuteRequest as WorkExecuteRequest,
)
from shyam.providers.zarya.models import (
    WorkExecuteResponse as WorkExecuteResponse,
)
from shyam.providers.zarya.models import (
    WorkStatusResponse as WorkStatusResponse,
)
from shyam.providers.zarya.provider import ZaryaProvider as ZaryaProvider

__all__ = [
    "EXPECTED_PROTOCOL",
    "PROVIDER_ID_ZARYA",
    "AuthInfoResponse",
    "CapabilitiesResponse",
    "CapabilityEntry",
    "EcosystemErrorCode",
    "EcosystemStatus",
    "IdentityResponse",
    "ProtocolResponse",
    "StatusResponse",
    "VerificationOutcome",
    "WorkExecuteRequest",
    "WorkExecuteResponse",
    "WorkStatusResponse",
    "ZaryaAuthenticationError",
    "ZaryaBusyError",
    "ZaryaClientError",
    "ZaryaConnectionError",
    "ZaryaProtocolError",
    "ZaryaProvider",
    "ZaryaToolNotAllowedError",
    "ZaryaUnavailableError",
    "ZaryaVerificationError",
    "map_capabilities_response",
    "map_ecosystem_status_to_availability",
    "map_to_shyam_provider",
]
