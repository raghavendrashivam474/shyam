"""Unit tests for S14 cryptographic signing and trust authentication gate."""

from pathlib import Path
from uuid import uuid4

import pytest

from shyam.events.bus import EventBus
from shyam.identity.crypto import KeyPair
from shyam.sync.authenticator import SyncAuthenticator
from shyam.sync.models import (
    NodeVersionMap,
    SyncEnvelope,
    SyncOutcome,
    SyncPayload,
)
from shyam.trust.models import RelationshipType
from shyam.trust.service import TrustService


@pytest.fixture
async def trust_service(tmp_path: Path) -> TrustService:
    service = TrustService(data_dir=tmp_path, event_bus=EventBus())
    await service.initialize()
    return service


@pytest.fixture
def authenticator(trust_service: TrustService) -> SyncAuthenticator:
    return SyncAuthenticator(trust_service=trust_service)


def _create_envelope(
    sender_id: str,
    pub_key: str,
    version_map: dict[str, int] | None = None,
) -> SyncEnvelope:
    return SyncEnvelope(
        sender_node_id=sender_id,
        sender_public_key=pub_key,
        message_type="sync_response",
        version_map=NodeVersionMap(versions=version_map or {sender_id: 1}),
        payload=SyncPayload(known_node_ids=[sender_id]),
        message_id=str(uuid4()),
    )


@pytest.mark.asyncio
async def test_sign_and_authenticate_trusted_peer(
    authenticator: SyncAuthenticator,
    trust_service: TrustService,
):
    sender_keypair = KeyPair.generate()
    sender_id = str(uuid4())

    # Grant trust
    await trust_service.grant_trust(
        node_id=sender_id,
        public_key=sender_keypair.public_key_b64,
        relationship=RelationshipType.PEER,
    )

    env = _create_envelope(sender_id, sender_keypair.public_key_b64)
    signed_env = authenticator.sign_envelope(env, sender_keypair)

    assert signed_env.is_signed()

    valid, outcome, detail = await authenticator.authenticate_incoming(signed_env)
    assert valid is True
    assert outcome == SyncOutcome.APPLIED


@pytest.mark.asyncio
async def test_reject_untrusted_peer(
    authenticator: SyncAuthenticator,
):
    sender_keypair = KeyPair.generate()
    sender_id = str(uuid4())

    env = _create_envelope(sender_id, sender_keypair.public_key_b64)
    signed_env = authenticator.sign_envelope(env, sender_keypair)

    valid, outcome, detail = await authenticator.authenticate_incoming(signed_env)
    assert valid is False
    assert outcome == SyncOutcome.REJECTED_UNTRUSTED


@pytest.mark.asyncio
async def test_reject_revoked_peer(
    authenticator: SyncAuthenticator,
    trust_service: TrustService,
):
    sender_keypair = KeyPair.generate()
    sender_id = str(uuid4())

    await trust_service.grant_trust(
        node_id=sender_id,
        public_key=sender_keypair.public_key_b64,
        relationship=RelationshipType.PEER,
    )
    await trust_service.revoke_trust(node_id=sender_id, reason="Compromised")

    env = _create_envelope(sender_id, sender_keypair.public_key_b64)
    signed_env = authenticator.sign_envelope(env, sender_keypair)

    valid, outcome, detail = await authenticator.authenticate_incoming(signed_env)
    assert valid is False
    assert outcome == SyncOutcome.REJECTED_REVOKED


@pytest.mark.asyncio
async def test_reject_tampered_payload_invalid_signature(
    authenticator: SyncAuthenticator,
    trust_service: TrustService,
):
    sender_keypair = KeyPair.generate()
    sender_id = str(uuid4())

    await trust_service.grant_trust(
        node_id=sender_id,
        public_key=sender_keypair.public_key_b64,
        relationship=RelationshipType.PEER,
    )

    env = _create_envelope(sender_id, sender_keypair.public_key_b64)
    signed_env = authenticator.sign_envelope(env, sender_keypair)

    # Tamper payload while keeping old signature
    tampered_payload = SyncPayload(known_node_ids=[sender_id, "malicious-node"])
    tampered_env = signed_env.model_copy(update={"payload": tampered_payload})

    valid, outcome, detail = await authenticator.authenticate_incoming(tampered_env)
    assert valid is False
    assert outcome == SyncOutcome.REJECTED_INVALID_SIGNATURE


@pytest.mark.asyncio
async def test_reject_mismatched_pinned_public_key(
    authenticator: SyncAuthenticator,
    trust_service: TrustService,
):
    sender_keypair = KeyPair.generate()
    imposter_keypair = KeyPair.generate()
    sender_id = str(uuid4())

    # Pinned with sender_keypair
    await trust_service.grant_trust(
        node_id=sender_id,
        public_key=sender_keypair.public_key_b64,
        relationship=RelationshipType.PEER,
    )

    # Signed with imposter_keypair claiming sender_id
    env = _create_envelope(sender_id, imposter_keypair.public_key_b64)
    signed_env = authenticator.sign_envelope(env, imposter_keypair)

    valid, outcome, detail = await authenticator.authenticate_incoming(signed_env)
    assert valid is False
    assert outcome == SyncOutcome.REJECTED_INVALID_SIGNATURE
