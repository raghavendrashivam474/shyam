"""Unit tests for S14 SyncService state convergence, idempotency, and loops."""

from pathlib import Path
from uuid import uuid4

import pytest

from shyam.events.bus import EventBus
from shyam.identity.crypto import KeyPair
from shyam.sync.events import SyncCompletedEvent, SyncRejectedEvent
from shyam.sync.models import SyncOutcome
from shyam.sync.service import SyncService
from shyam.trust.models import RelationshipType
from shyam.trust.service import TrustService


@pytest.fixture
async def create_node(tmp_path: Path):
    """Factory fixture to create independent authenticated Shyam nodes."""
    async def _factory(node_name: str = "node") -> tuple[SyncService, KeyPair, TrustService, EventBus, str]:
        node_id = str(uuid4())
        keypair = KeyPair.generate()
        bus = EventBus()
        node_dir = tmp_path / node_name
        node_dir.mkdir(parents=True, exist_ok=True)
        trust_service = TrustService(data_dir=node_dir, event_bus=bus)
        await trust_service.initialize()

        # Self-trust
        await trust_service.grant_trust(
            node_id=node_id,
            public_key=keypair.public_key_b64,
            relationship=RelationshipType.PERSONAL,
        )

        service = SyncService(
            local_node_id=node_id,
            keypair=keypair,
            trust_service=trust_service,
            event_bus=bus,
        )
        return service, keypair, trust_service, bus, node_id

    return _factory


@pytest.mark.asyncio
async def test_trusted_peer_state_convergence(create_node):
    # Setup Node A and Node B
    service_a, keypair_a, trust_a, bus_a, id_a = await create_node("node_a")
    service_b, keypair_b, trust_b, bus_b, id_b = await create_node("node_b")

    # Establish mutual trust
    await trust_a.grant_trust(node_id=id_b, public_key=keypair_b.public_key_b64, relationship=RelationshipType.PEER)
    await trust_b.grant_trust(node_id=id_a, public_key=keypair_a.public_key_b64, relationship=RelationshipType.PEER)

    # Node A discovers some capabilities
    await service_a.update_local_facts(
        capabilities={id_a: ["cap.speech", "cap.audio"]},
        availability={id_a: "available"},
    )

    # Node A creates signed envelope
    envelope_a = await service_a.create_sync_envelope()
    assert envelope_a.is_signed()

    # Node B processes envelope from Node A
    result_b = await service_b.process_incoming_envelope(envelope_a)
    assert result_b.outcome == SyncOutcome.APPLIED

    # Node B now knows Node A's capabilities
    caps_b_view = await service_b.get_node_capabilities(id_a)
    assert caps_b_view == ["cap.audio", "cap.speech"]
    status_b_view = await service_b.get_node_availability(id_a)
    assert status_b_view == "available"


@pytest.mark.asyncio
async def test_idempotency_duplicate_messages_ignored(create_node):
    service_a, keypair_a, trust_a, _, id_a = await create_node("node_a")
    service_b, keypair_b, trust_b, _, id_b = await create_node("node_b")

    await trust_b.grant_trust(node_id=id_a, public_key=keypair_a.public_key_b64, relationship=RelationshipType.PEER)
    await service_a.update_local_facts(capabilities={id_a: ["cap.ai"]})

    envelope = await service_a.create_sync_envelope()

    # First delivery -> APPLIED
    res1 = await service_b.process_incoming_envelope(envelope)
    assert res1.outcome == SyncOutcome.APPLIED

    # Second delivery with identical envelope -> ALREADY_CURRENT
    res2 = await service_b.process_incoming_envelope(envelope)
    assert res2.outcome == SyncOutcome.ALREADY_CURRENT

    # Third delivery -> ALREADY_CURRENT
    res3 = await service_b.process_incoming_envelope(envelope)
    assert res3.outcome == SyncOutcome.ALREADY_CURRENT


@pytest.mark.asyncio
async def test_sync_loop_prevention(create_node):
    service_a, keypair_a, trust_a, _, id_a = await create_node("node_a")
    service_b, keypair_b, trust_b, _, id_b = await create_node("node_b")

    await trust_a.grant_trust(node_id=id_b, public_key=keypair_b.public_key_b64, relationship=RelationshipType.PEER)
    await trust_b.grant_trust(node_id=id_a, public_key=keypair_a.public_key_b64, relationship=RelationshipType.PEER)

    await service_a.update_local_facts(capabilities={id_a: ["cap.sensor"]})

    # A -> B
    env_a = await service_a.create_sync_envelope()
    res_b = await service_b.process_incoming_envelope(env_a)
    assert res_b.outcome == SyncOutcome.APPLIED

    # B replies with its updated view -> A
    env_b = await service_b.create_sync_envelope()
    res_a = await service_a.process_incoming_envelope(env_b)

    # A detects that it is already current or ahead, terminating loop!
    assert res_a.outcome == SyncOutcome.ALREADY_CURRENT


@pytest.mark.asyncio
async def test_reject_untrusted_node_sync(create_node):
    service_a, keypair_a, _, _, id_a = await create_node("node_a")
    service_b, _, _, bus_b, _ = await create_node("node_b")

    # Node B does NOT trust Node A
    rejected_events = []

    async def _on_rejected(ev: SyncRejectedEvent):
        rejected_events.append(ev)

    await bus_b.subscribe(SyncRejectedEvent, _on_rejected)

    envelope_a = await service_a.create_sync_envelope()
    result = await service_b.process_incoming_envelope(envelope_a)

    assert result.outcome == SyncOutcome.REJECTED_UNTRUSTED
    assert len(rejected_events) == 1
    assert rejected_events[0].sender_node_id == id_a


@pytest.mark.asyncio
async def test_concurrent_divergent_states_merge(create_node):
    service_a, keypair_a, trust_a, _, id_a = await create_node("node_a")
    service_b, keypair_b, trust_b, _, id_b = await create_node("node_b")

    await trust_a.grant_trust(node_id=id_b, public_key=keypair_b.public_key_b64, relationship=RelationshipType.PEER)
    await trust_b.grant_trust(node_id=id_a, public_key=keypair_a.public_key_b64, relationship=RelationshipType.PEER)

    # Both mutate independently
    await service_a.update_local_facts(capabilities={id_a: ["cap.camera"]})
    await service_b.update_local_facts(capabilities={id_b: ["cap.display"]})

    # Exchange B -> A
    env_b = await service_b.create_sync_envelope()
    res_a = await service_a.process_incoming_envelope(env_b)
    assert res_a.outcome == SyncOutcome.CONFLICT  # CONCURRENT detected & merged

    # A now has both
    caps_a = await service_a.get_node_capabilities(id_a)
    caps_b = await service_a.get_node_capabilities(id_b)
    assert caps_a == ["cap.camera"]
    assert caps_b == ["cap.display"]
