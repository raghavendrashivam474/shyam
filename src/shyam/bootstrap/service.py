"""Device Bootstrap & Recovery Service implementation — S15."""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from shyam.bootstrap.errors import (
    BootstrapError,
    BootstrapRejectedError,
    RecoveryError,
)
from shyam.bootstrap.models import (
    BootstrapOutcome,
    BootstrapRequest,
    BootstrapResponse,
    BootstrapSession,
    BootstrapState,
    RecoveryRequest,
    RecoveryResult,
    RecoveryScenario,
)
from shyam.identity.crypto import KeyPair
from shyam.trust.models import RelationshipType, TrustStatus

if TYPE_CHECKING:
    from shyam.bootstrap.transport import BootstrapTransport
    from shyam.events.bus import EventBus
    from shyam.identity.manager import IdentityManager
    from shyam.sync.service import SyncService
    from shyam.trust.service import TrustService

logger = logging.getLogger("shyam.bootstrap.service")


class BootstrapService:
    """Service managing device bootstrap and recovery lifecycles."""

    def __init__(
        self,
        identity_manager: IdentityManager,
        trust_service: TrustService,
        sync_service_getter: Callable[[], SyncService | None],
        event_bus: EventBus | None = None,
    ) -> None:
        self._identity_manager = identity_manager
        self._trust_service = trust_service
        self._sync_service_getter = sync_service_getter
        self._event_bus = event_bus
        self._sessions: dict[str, BootstrapSession] = {}
        self._lock = asyncio.Lock()

    async def handle_incoming_request(
        self,
        request: BootstrapRequest,
    ) -> BootstrapResponse:
        """Process an incoming BootstrapRequest on the authority side."""
        logger.info(
            "Processing bootstrap request %s from %s",
            request.request_id,
            request.node_id,
        )

        # 1. Cryptographic Signature Verification
        try:
            signable = f"{request.request_id}:{request.node_id}:{request.public_key}:{request.timestamp.isoformat()}"
            is_valid = KeyPair.verify_with_public_key(
                public_key_b64=request.public_key,
                data=signable.encode("utf-8"),
                signature=base64.b64decode(request.signature),
            )
        except Exception as e:
            logger.warning(
                "Signature parse/verify failure on request %s: %s",
                request.request_id,
                e,
            )
            return BootstrapResponse(
                request_id=request.request_id,
                accepted=False,
                rejection_reason=f"Signature validation error: {e}",
                outcome=BootstrapOutcome.REJECTED_SIGNATURE,
            )

        if not is_valid:
            logger.warning(
                "Invalid Ed25519 signature on request %s",
                request.request_id,
            )
            return BootstrapResponse(
                request_id=request.request_id,
                accepted=False,
                rejection_reason="Cryptographic signature verification failed",
                outcome=BootstrapOutcome.REJECTED_SIGNATURE,
            )

        # 2. Check S13 Trust standing
        record = await self._trust_service.get_record(request.node_id)
        if record.status == TrustStatus.REVOKED:
            logger.warning("Rejected revoked node %s", request.node_id)
            return BootstrapResponse(
                request_id=request.request_id,
                accepted=False,
                rejection_reason=f"Node '{request.node_id}' is REVOKED",
                outcome=BootstrapOutcome.REJECTED_REVOKED,
            )

        # 3. Grant peer trust in S13
        await self._trust_service.grant_trust(
            node_id=request.node_id,
            public_key=request.public_key,
            relationship=RelationshipType.PEER,
            alias=request.node_name or f"node-{request.node_id[:8]}",
        )

        # 4. Return authority identity for mutual trust
        local_id = self._identity_manager.identity
        sync_svc = self._sync_service_getter()
        auth_pub_key = ""
        if sync_svc and hasattr(sync_svc, "_keypair"):
            auth_pub_key = sync_svc._keypair.public_key_b64

        return BootstrapResponse(
            request_id=request.request_id,
            accepted=True,
            authority_node_id=str(local_id.node_id) if local_id else "",
            authority_public_key=auth_pub_key,
            outcome=BootstrapOutcome.SUCCESS,
        )

    async def execute_client_bootstrap(
        self,
        authority_endpoint: str,
        transport: BootstrapTransport,
    ) -> BootstrapSession:
        """Initiate and coordinate client-side bootstrap with an authority."""
        session = BootstrapSession()
        async with self._lock:
            self._sessions[session.session_id] = session

        session = session.transition(BootstrapState.IDENTITY_READY)
        session = session.transition(BootstrapState.BOOTSTRAP_REQUESTED)

        local_identity = self._identity_manager.identity
        if not local_identity:
            raise BootstrapError("Local logical identity is missing")

        sync_svc = self._sync_service_getter()
        if not sync_svc:
            raise BootstrapError("SyncService is not initialized")

        req_id = session.session_id
        timestamp = session.created_at
        node_id_str = str(local_identity.node_id)
        pub_key = sync_svc._keypair.public_key_b64

        signable = f"{req_id}:{node_id_str}:{pub_key}:{timestamp.isoformat()}"
        signature_bytes = sync_svc._keypair.sign(signable.encode("utf-8"))
        signature_b64 = base64.b64encode(signature_bytes).decode("ascii")

        request = BootstrapRequest(
            request_id=req_id,
            node_id=node_id_str,
            public_key=pub_key,
            node_name=local_identity.node_name,
            timestamp=timestamp,
            signature=signature_b64,
        )

        session = session.transition(BootstrapState.AUTHENTICATING)

        try:
            response = await transport.send_request(authority_endpoint, request)
        except Exception as e:
            session = session.transition(BootstrapState.FAILED)
            async with self._lock:
                self._sessions[session.session_id] = session
            raise BootstrapError(f"Transport transmission failed: {e}") from e

        if not response.accepted:
            session = session.transition(BootstrapState.REJECTED)
            async with self._lock:
                self._sessions[session.session_id] = session
            raise BootstrapRejectedError(node_id_str, response.rejection_reason)

        session = session.transition(BootstrapState.TRUST_ESTABLISHED)

        # Grant local trust to authority
        await self._trust_service.grant_trust(
            node_id=response.authority_node_id,
            public_key=response.authority_public_key,
            relationship=RelationshipType.INFRASTRUCTURE,
            alias="Bootstrap Authority",
        )

        session = session.transition(BootstrapState.STATE_INITIALIZING)
        session = session.transition(BootstrapState.SYNCING)

        try:
            await sync_svc.increment_local_version()
        except Exception as e:
            session = session.transition(BootstrapState.FAILED)
            async with self._lock:
                self._sessions[session.session_id] = session
            raise BootstrapError(f"Initial synchronization failed: {e}") from e

        session = session.transition(BootstrapState.READY)
        async with self._lock:
            self._sessions[session.session_id] = session

        return session

    async def recover_device(
        self,
        request: RecoveryRequest,
        authority_endpoint: str | None = None,
        transport: BootstrapTransport | None = None,
    ) -> RecoveryResult:
        """Evaluate and run recovery for a device that lost partial or total state."""
        logger.info(
            "Executing device recovery for scenario: %s",
            request.scenario,
        )

        if request.scenario == RecoveryScenario.IDENTITY_LOST:
            # Force generate and persist a fresh identity rather than loading existing disk cache
            new_id = self._identity_manager._create_and_persist_identity()
            self._identity_manager._identity = new_id
            return RecoveryResult(
                request_id=request.request_id,
                success=True,
                scenario=request.scenario,
                new_node_id=str(new_id.node_id),
                detail="Identity lost. Generated fresh cryptographic identity and enrollment path.",
            )

        if request.scenario == RecoveryScenario.STATE_LOST_IDENTITY_INTACT:
            sync_svc = self._sync_service_getter()
            if not sync_svc:
                raise RecoveryError("SyncService is not active. Cannot execute recovery.")

            await sync_svc.increment_local_version()
            return RecoveryResult(
                request_id=request.request_id,
                success=True,
                scenario=request.scenario,
                new_node_id=request.existing_node_id,
                detail="Identity intact. Re-synchronized version maps and restored facts.",
            )

        return RecoveryResult(
            request_id=request.request_id,
            success=False,
            scenario=request.scenario,
            detail="Unsupported or unknown recovery scenario",
        )