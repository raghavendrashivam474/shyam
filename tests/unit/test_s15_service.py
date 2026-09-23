"""Unit tests for S15 BootstrapService lifecycle, authority evaluation, and recovery."""

import base64
import pytest
from uuid import uuid4
from pathlib import Path

from shyam.bootstrap.errors import (
    BootstrapError,
    BootstrapRejectedError,
)
from shyam.bootstrap.models import (
    BootstrapOutcome,
    BootstrapRequest,
    BootstrapResponse,
    BootstrapState,
    RecoveryRequest,
    RecoveryScenario,
)
from shyam.bootstrap.service import BootstrapService
from shyam.bootstrap.transport import BootstrapTransport
from shyam.identity.crypto import KeyPair
from shyam.identity.manager import IdentityManager
from shyam.trust.models import RelationshipType, TrustStatus
from shyam.trust.service import TrustService
from shyam.sync.service import SyncService


class InMemoryTransport(BootstrapTransport):
    """Simulated transport connecting client directly to an authority service."""

    def __init__(self, authority_service: BootstrapService) -> None:
        self.authority = authority_service

    async def send_request(
        self,
        endpoint_id: str,
        request: BootstrapRequest,
    ) -> BootstrapResponse:
        return await self.authority.handle_incoming_request(request)


class FailingTransport(BootstrapTransport):
    """Transport that throws a connection exception."""

    async def send_request(
        self,
        endpoint_id: str,
        request: BootstrapRequest,
    ) -> BootstrapResponse:
        raise ConnectionError("Network unreachable")


@pytest.fixture
def test_env(tmp_path: Path):
    """Create test identity, trust, and sync services."""
    auth_dir = tmp_path / "authority"
    client_dir = tmp_path / "client"

    # Authority components
    auth_id_mgr = IdentityManager(data_dir=auth_dir, custom_node_name="authority-node")
    auth_identity = auth_id_mgr.get_or_create_identity()
    auth_kp = KeyPair.generate()
    auth_trust = TrustService(data_dir=auth_dir)
    auth_sync = SyncService(
        local_node_id=auth_identity.node_id,
        keypair=auth_kp,
        trust_service=auth_trust,
    )
    auth_service = BootstrapService(
        identity_manager=auth_id_mgr,
        trust_service=auth_trust,
        sync_service_getter=lambda: auth_sync,
    )

    # Client components
    client_id_mgr = IdentityManager(data_dir=client_dir, custom_node_name="client-device")
    client_identity = client_id_mgr.get_or_create_identity()
    client_kp = KeyPair.generate()
    client_trust = TrustService(data_dir=client_dir)
    client_sync = SyncService(
        local_node_id=client_identity.node_id,
        keypair=client_kp,
        trust_service=client_trust,
    )
    client_service = BootstrapService(
        identity_manager=client_id_mgr,
        trust_service=client_trust,
        sync_service_getter=lambda: client_sync,
    )

    return {
        "auth_service": auth_service,
        "auth_trust": auth_trust,
        "auth_id": auth_identity,
        "client_service": client_service,
        "client_trust": client_trust,
        "client_id": client_identity,
        "client_kp": client_kp,
        "client_id_mgr": client_id_mgr,
    }


@pytest.mark.asyncio
async def test_authority_handles_valid_bootstrap_request(test_env) -> None:
    auth_service = test_env["auth_service"]
    auth_trust = test_env["auth_trust"]
    client_id = str(test_env["client_id"].node_id)
    client_kp = test_env["client_kp"]

    req_id = str(uuid4())
    from datetime import datetime, UTC
    ts = datetime.now(UTC)
    signable = f"{req_id}:{client_id}:{client_kp.public_key_b64}:{ts.isoformat()}"
    sig = base64.b64encode(client_kp.sign(signable.encode("utf-8"))).decode("ascii")

    req = BootstrapRequest(
        request_id=req_id,
        node_id=client_id,
        public_key=client_kp.public_key_b64,
        node_name="new-laptop",
        timestamp=ts,
        signature=sig,
    )

    resp = await auth_service.handle_incoming_request(req)
    assert resp.accepted
    assert resp.outcome == BootstrapOutcome.SUCCESS
    assert resp.authority_node_id == str(test_env["auth_id"].node_id)

    # Check S13 trust record created on authority
    record = await auth_trust.get_record(client_id)
    assert record.is_trusted
    assert record.relationship == RelationshipType.PEER


@pytest.mark.asyncio
async def test_authority_rejects_invalid_signature(test_env) -> None:
    auth_service = test_env["auth_service"]
    client_id = str(test_env["client_id"].node_id)
    client_kp = test_env["client_kp"]

    req = BootstrapRequest(
        node_id=client_id,
        public_key=client_kp.public_key_b64,
        signature="invalid_base64_sig==",
    )

    resp = await auth_service.handle_incoming_request(req)
    assert not resp.accepted
    assert resp.outcome == BootstrapOutcome.REJECTED_SIGNATURE


@pytest.mark.asyncio
async def test_authority_rejects_revoked_node(test_env) -> None:
    auth_service = test_env["auth_service"]
    auth_trust = test_env["auth_trust"]
    client_id = str(test_env["client_id"].node_id)
    client_kp = test_env["client_kp"]

    # Explicitly revoke node in authority trust store first
    await auth_trust.revoke_trust(node_id=client_id, reason="Compromised node")

    from datetime import datetime, UTC
    req_id = str(uuid4())
    ts = datetime.now(UTC)
    signable = f"{req_id}:{client_id}:{client_kp.public_key_b64}:{ts.isoformat()}"
    sig = base64.b64encode(client_kp.sign(signable.encode("utf-8"))).decode("ascii")

    req = BootstrapRequest(
        request_id=req_id,
        node_id=client_id,
        public_key=client_kp.public_key_b64,
        timestamp=ts,
        signature=sig,
    )

    resp = await auth_service.handle_incoming_request(req)
    assert not resp.accepted
    assert resp.outcome == BootstrapOutcome.REJECTED_REVOKED


@pytest.mark.asyncio
async def test_full_client_bootstrap_flow(test_env) -> None:
    client_service = test_env["client_service"]
    auth_service = test_env["auth_service"]
    client_trust = test_env["client_trust"]

    transport = InMemoryTransport(auth_service)
    session = await client_service.execute_client_bootstrap("mock://auth", transport)

    assert session.state == BootstrapState.READY
    assert session.is_successful

    # Confirm client now trusts authority node locally
    auth_id_str = str(test_env["auth_id"].node_id)
    record = await client_trust.get_record(auth_id_str)
    assert record.is_trusted


@pytest.mark.asyncio
async def test_client_bootstrap_handles_transport_failure(test_env) -> None:
    client_service = test_env["client_service"]
    failing_transport = FailingTransport()

    with pytest.raises(BootstrapError, match="Transport transmission failed"):
        await client_service.execute_client_bootstrap("mock://auth", failing_transport)


@pytest.mark.asyncio
async def test_recovery_state_lost_identity_intact(test_env) -> None:
    client_service = test_env["client_service"]
    client_id_str = str(test_env["client_id"].node_id)

    req = RecoveryRequest(
        scenario=RecoveryScenario.STATE_LOST_IDENTITY_INTACT,
        existing_node_id=client_id_str,
    )

    res = await client_service.recover_device(req)
    assert res.success
    assert res.new_node_id == client_id_str
    assert "Identity intact" in res.detail


@pytest.mark.asyncio
async def test_recovery_identity_lost_re_enrolls_cleanly(test_env) -> None:
    client_service = test_env["client_service"]
    old_node_id = str(test_env["client_id"].node_id)

    req = RecoveryRequest(
        scenario=RecoveryScenario.IDENTITY_LOST,
        existing_node_id=old_node_id,
    )

    res = await client_service.recover_device(req)
    assert res.success
    # Must generate a completely new node ID
    assert res.new_node_id != ""
    assert res.new_node_id != old_node_id