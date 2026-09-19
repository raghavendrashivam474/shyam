"""Flux Gateway HTTP Client (S7).

Handles transport, request/response serialization, and structured error
parsing for the Flux Gateway API v1 contract (ADR-007).
Completely decoupled from Shyam's internal orchestration logic.

Uses only stdlib (urllib) — no external HTTP dependencies.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from shyam.providers.flux.exceptions import (
    FluxClientError,
    FluxConnectionError,
    FluxPeerNotFoundError,
    FluxProtocolError,
    FluxTransferError,
    FluxUnavailableError,
)
from shyam.providers.flux.models import (
    FluxCancelResponse,
    FluxConnectRequest,
    FluxConnectResponse,
    FluxIdentityResponse,
    FluxPeerInfo,
    FluxPeersResponse,
    FluxStatusResponse,
    FluxTransferRequest,
    FluxTransferResponse,
    FluxTransferStatusResponse,
)

logger = logging.getLogger(__name__)


class FluxClient:
    """HTTP Client for the Flux Gateway API v1 (ADR-007)."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:9100/flux/v1",
        timeout: float = 10.0,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: Base HTTP URL of the Flux Gateway endpoint.
            timeout: Network timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ── Internal transport ───────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform an HTTP request and parse the response or errors."""
        url = f"{self.base_url}{path}"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

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
            self._handle_http_error(e)

        except urllib.error.URLError as e:
            raise FluxConnectionError(
                f"Cannot reach Flux Gateway at {self.base_url}. "
                f"Is Flux running? Details: {e.reason}"
            ) from e

        except FluxClientError:
            raise

        except Exception as e:
            raise FluxClientError(
                f"Unexpected transport failure: {e}",
            ) from e

        # Unreachable, but satisfies type checkers
        return {}  # pragma: no cover

    def _handle_http_error(self, e: urllib.error.HTTPError) -> None:
        """Parse HTTP errors into typed Flux exceptions."""
        try:
            err_bytes = e.read()
            err_json = json.loads(err_bytes.decode("utf-8"))
            code = err_json.get("code", "unknown")
            message = err_json.get("message", str(e))
        except Exception:
            code = "unknown"
            message = f"HTTP {e.code}: {e.reason}"

        if e.code == 404 and "peer" in code:
            raise FluxPeerNotFoundError(err_json.get("detail", {}).get("peer_id", "unknown")) from e
        elif e.code == 409 and "protocol" in code:
            raise FluxProtocolError(message) from e
        elif e.code == 503:
            raise FluxUnavailableError(message) from e
        elif "transfer" in code:
            raise FluxTransferError(message) from e
        else:
            raise FluxClientError(
                message,
                code=code,
                http_status=e.code,
                detail=err_json if "err_json" in dir() else None,
            ) from e

    # ── Gateway API v1 Methods ───────────────────────────────────

    def get_identity(self) -> FluxIdentityResponse:
        """GET /flux/v1/identity"""
        data = self._request("GET", "/identity")
        return FluxIdentityResponse.model_validate(data)

    def get_status(self) -> FluxStatusResponse:
        """GET /flux/v1/status"""
        data = self._request("GET", "/status")
        return FluxStatusResponse.model_validate(data)

    def get_peers(self) -> FluxPeersResponse:
        """GET /flux/v1/peers"""
        data = self._request("GET", "/peers")
        return FluxPeersResponse.model_validate(data)

    def get_peer(self, peer_id: str) -> FluxPeerInfo:
        """GET /flux/v1/peers/{peer_id}"""
        data = self._request("GET", f"/peers/{peer_id}")
        return FluxPeerInfo.model_validate(data)

    def connect_peer(self, peer_id: str) -> FluxConnectResponse:
        """POST /flux/v1/connect"""
        req = FluxConnectRequest(peer_id=peer_id)
        data = self._request("POST", "/connect", data=req.model_dump())
        return FluxConnectResponse.model_validate(data)

    def initiate_transfer(
        self,
        peer_id: str,
        artifact_path: str,
        artifact_name: str | None = None,
        is_directory: bool = False,
    ) -> FluxTransferResponse:
        """POST /flux/v1/transfer"""
        req = FluxTransferRequest(
            peer_id=peer_id,
            artifact_path=artifact_path,
            artifact_name=artifact_name,
            is_directory=is_directory,
        )
        data = self._request("POST", "/transfer", data=req.model_dump())
        return FluxTransferResponse.model_validate(data)

    def get_transfer_status(
        self,
        transfer_id: str,
    ) -> FluxTransferStatusResponse:
        """GET /flux/v1/transfer/{transfer_id}"""
        data = self._request("GET", f"/transfer/{transfer_id}")
        return FluxTransferStatusResponse.model_validate(data)

    def cancel_transfer(
        self,
        transfer_id: str,
    ) -> FluxCancelResponse:
        """POST /flux/v1/transfer/{transfer_id}/cancel"""
        data = self._request("POST", f"/transfer/{transfer_id}/cancel")
        return FluxCancelResponse.model_validate(data)
