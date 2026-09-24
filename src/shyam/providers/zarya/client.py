"""Zarya EIP-1 HTTP Client - S6.

Handles transport, authentication, header injection, request/response
serialization, and structured error parsing for the Zarya EIP-1 protocol.
It is completely decoupled from Shyam's internal orchestration logic.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from shyam.providers.zarya.exceptions import (
    ZaryaAuthenticationError,
    ZaryaBusyError,
    ZaryaClientError,
    ZaryaConnectionError,
    ZaryaToolNotAllowedError,
    ZaryaUnavailableError,
    ZaryaVerificationError,
)
from shyam.providers.zarya.models import (
    AuthInfoResponse,
    CapabilitiesResponse,
    EcosystemErrorCode,
    EcosystemErrorEnvelope,
    IdentityResponse,
    ProtocolResponse,
    StatusResponse,
    VerificationOutcome,
    WorkExecuteRequest,
    WorkExecuteResponse,
    WorkStatusResponse,
    ContinuationRequest,
    ContinuationResponse,
)

logger = logging.getLogger(__name__)


class ZaryaClient:
    """HTTP Client for the Zarya EIP-1 (zarya-ecosystem / eip-1.0)."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8765/ecosystem/v1",
        token: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: Base HTTP URL of the Zarya ecosystem endpoint.
            token: Ecosystem auth token. Falls back to
                   ZARYA_ECOSYSTEM_TOKEN env var if not provided.
            timeout: Network timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.token = token or os.environ.get("ZARYA_ECOSYSTEM_TOKEN", "")
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        auth_required: bool = True,
    ) -> dict[str, Any]:
        """Perform an HTTP request and parse the response or errors."""
        url = f"{self.base_url}{path}"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if auth_required:
            if not self.token:
                raise ZaryaAuthenticationError("No ecosystem token configured.")
            headers["X-Ecosystem-Token"] = self.token

        req_data = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(
            url,
            data=req_data,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_bytes = resp.read()
                if not resp_bytes:
                    return {}
                return json.loads(resp_bytes.decode("utf-8"))

        except urllib.error.HTTPError as e:
            try:
                err_bytes = e.read()
                err_json = json.loads(err_bytes.decode("utf-8"))
                self._handle_structured_error(e.code, err_json)
            except ZaryaClientError:
                raise
            except Exception as parse_err:
                logger.debug(
                    "Failed to parse structured error: %s",
                    parse_err,
                )
                self._handle_http_status_fallback(e.code, str(e))
                raise ZaryaClientError(
                    f"HTTP error {e.code}: {e.reason}",
                    http_status=e.code,
                ) from e

        except urllib.error.URLError as e:
            raise ZaryaConnectionError(
                f"Cannot reach Zarya at {self.base_url}. Is Zarya running? Details: {e.reason}"
            ) from e
        except Exception as e:
            raise ZaryaClientError(
                f"Unexpected transport failure: {e}",
            ) from e

    def _handle_structured_error(
        self,
        status_code: int,
        error_data: dict[str, Any],
    ) -> None:
        """Parse EIP-1 structured errors and raise typed exceptions."""
        detail = error_data.get("detail", {})
        if "error" not in detail:
            raise ZaryaClientError(
                f"HTTP {status_code}: {error_data}",
                http_status=status_code,
            )

        try:
            envelope = EcosystemErrorEnvelope.model_validate(detail)
            err = envelope.error
        except Exception as e:
            raise ZaryaClientError(
                f"Failed to validate EIP-1 error model: {e}",
                http_status=status_code,
                detail=error_data,
            ) from e

        if err.code == EcosystemErrorCode.UNAUTHORIZED:
            raise ZaryaAuthenticationError(err.message)
        elif err.code == EcosystemErrorCode.TOOL_NOT_ALLOWED:
            allowed = err.detail.get("allowed_tools", [])
            tool = err.message.split("'")[1] if "'" in err.message else "unknown"
            raise ZaryaToolNotAllowedError(
                tool=tool,
                allowed_tools=allowed,
            )
        elif err.code == EcosystemErrorCode.BUSY:
            raise ZaryaBusyError(err.message)
        elif err.code == EcosystemErrorCode.UNAVAILABLE:
            raise ZaryaUnavailableError(err.message)
        else:
            raise ZaryaClientError(
                err.message,
                code=err.code,
                http_status=status_code,
                detail=err.detail,
            )

    def _handle_http_status_fallback(
        self,
        status_code: int,
        message: str,
    ) -> None:
        """Fallback handler if response body is not structured."""
        if status_code == 401:
            raise ZaryaAuthenticationError()
        elif status_code == 403:
            raise ZaryaClientError(
                "Access forbidden.",
                code=EcosystemErrorCode.TOOL_NOT_ALLOWED,
                http_status=403,
            )
        elif status_code == 404:
            raise ZaryaClientError(
                "Not found.",
                code=EcosystemErrorCode.OPERATION_NOT_SUPPORTED,
                http_status=404,
            )
        elif status_code == 503:
            raise ZaryaUnavailableError("Service unavailable fallback.")

    # ── EIP-1 Methods ────────────────────────────────────────

    def get_auth_info(self) -> AuthInfoResponse:
        """GET /ecosystem/v1/auth-info (unauthenticated)."""
        data = self._request("GET", "/auth-info", auth_required=False)
        return AuthInfoResponse.model_validate(data)

    def get_identity(self) -> IdentityResponse:
        """GET /ecosystem/v1/identity."""
        data = self._request("GET", "/identity")
        return IdentityResponse.model_validate(data)

    def get_protocol(self) -> ProtocolResponse:
        """GET /ecosystem/v1/protocol."""
        data = self._request("GET", "/protocol")
        return ProtocolResponse.model_validate(data)

    def get_capabilities(self) -> CapabilitiesResponse:
        """GET /ecosystem/v1/capabilities."""
        data = self._request("GET", "/capabilities")
        return CapabilitiesResponse.model_validate(data)

    def get_status(self) -> StatusResponse:
        """GET /ecosystem/v1/status."""
        data = self._request("GET", "/status")
        return StatusResponse.model_validate(data)

    def execute_work(
        self,
        tool: str,
        args: dict[str, Any] | None = None,
    ) -> WorkExecuteResponse:
        """POST /ecosystem/v1/work/execute.

        Note: HTTP 200 does not equal verification success.
        The response carries outcome and verified properties.
        """
        req_model = WorkExecuteRequest(tool=tool, args=args or {})
        data = self._request(
            "POST",
            "/work/execute",
            data=req_model.model_dump(),
        )
        resp = WorkExecuteResponse.model_validate(data)

        if resp.outcome == VerificationOutcome.VERIFIED_FAILURE:
            raise ZaryaVerificationError(
                tool=resp.tool,
                outcome=resp.outcome,
                summary=resp.summary,
            )

        return resp

    def get_work_status(self, operation_id: str) -> WorkStatusResponse:
        """GET /ecosystem/v1/work/status/{operation_id}."""
        data = self._request("GET", f"/work/status/{operation_id}")
        return WorkStatusResponse.model_validate(data)

    # ── N4 Continuation (S16) ────────────────────────────────

    def continue_work(
        self,
        portable_work: dict[str, Any],
        source_device_id: str = "",
        continuity_id: str = "",
    ) -> ContinuationResponse:
        """POST /ecosystem/v1/work/continue.

        Invokes Zarya N4 continue_portable_work on the target node.
        The target's internal pipeline (VALIDATE -> SUPPORT_CHECK ->
        RESOLVE -> AUTHORIZE -> RECONSTRUCT -> EXECUTE) runs inside
        Zarya. This client only sends the request and parses the
        response.

        Note: HTTP 200 does not equal continuation success.
        Inspect the outcome field.
        """
        req_model = ContinuationRequest(
            portable_work=portable_work,
            source_device_id=source_device_id,
            continuity_id=continuity_id,
        )
        data = self._request(
            "POST",
            "/work/continue",
            data=req_model.model_dump(),
        )
        return ContinuationResponse.model_validate(data)