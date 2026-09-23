"""Transport abstraction for Bootstrap handshake — S15."""

from __future__ import annotations

from typing import Protocol

from shyam.bootstrap.models import BootstrapRequest, BootstrapResponse


class BootstrapTransport(Protocol):
    """Pluggable transport abstraction for carrying bootstrap exchanges.

    Allows bootstrap handshakes to travel over in-process test rigs,
    local sockets, or future Flux protocols without altering S15 service logic.
    """

    async def send_request(
        self,
        endpoint_id: str,
        request: BootstrapRequest,
    ) -> BootstrapResponse:
        """Send a BootstrapRequest and await a BootstrapResponse."""
        ...