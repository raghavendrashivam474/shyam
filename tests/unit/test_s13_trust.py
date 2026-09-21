"""Unit tests for S13 Trust domain, store, and service."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from shyam.events.bus import EventBus
from shyam.trust.models import (
    RelationshipType,
    TrustGrantedEvent,
    TrustRecord,
    TrustRevokedEvent,
    TrustStatus,
)
from shyam.trust.service import TrustService
from shyam.trust.store import TrustStore, TrustStoreCorruptionError


class TestTrustRecordModel:
    """TrustRecord immutability and state transitions."""

    def test_default_status_unknown(self) -> None:
        rec = TrustRecord(node_id="n1")
        assert rec.status == TrustStatus.UNKNOWN
        assert not rec.is_trusted
        assert not rec.is_revoked

    def test_with_status_creates_new_record(self) -> None:
        rec = TrustRecord(node_id="n1")
        trusted = rec.with_status(TrustStatus.TRUSTED)
        assert rec.status == TrustStatus.UNKNOWN  # original unchanged
        assert trusted.status == TrustStatus.TRUSTED
        assert trusted.is_trusted

    def test_revoke_transition(self) -> None:
        rec = TrustRecord(node_id="n1", status=TrustStatus.TRUSTED)
        revoked = rec.with_status(TrustStatus.REVOKED)
        assert revoked.is_revoked
        assert not revoked.is_trusted

    def test_is_frozen(self) -> None:
        rec = TrustRecord(node_id="n1")
        with pytest.raises(Exception):
            rec.status = TrustStatus.TRUSTED  # type: ignore[misc]


class TestTrustStore:
    """TrustStore persistence and corruption handling."""

    def test_load_empty_when_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TrustStore(Path(tmp))
            assert store.load() == {}

    def test_save_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TrustStore(Path(tmp))
            records = {
                "n1": TrustRecord(node_id="n1", status=TrustStatus.TRUSTED),
                "n2": TrustRecord(node_id="n2", status=TrustStatus.REVOKED),
            }
            store.save(records)
            loaded = store.load()
            assert loaded["n1"].status == TrustStatus.TRUSTED
            assert loaded["n2"].status == TrustStatus.REVOKED

    def test_corrupted_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TrustStore(Path(tmp))
            (Path(tmp) / "trust_store.json").write_text("NOT JSON", encoding="utf-8")
            with pytest.raises(TrustStoreCorruptionError):
                store.load()


class TestTrustService:
    """TrustService state machine and event emission."""

    @pytest.fixture
    def service(self) -> TrustService:
        """Create a fresh TrustService in a temp directory."""
        tmp = tempfile.mkdtemp()
        return TrustService(data_dir=Path(tmp))

    @pytest.mark.asyncio
    async def test_unknown_by_default(self, service: TrustService) -> None:
        await service.initialize()
        rec = await service.get_record("unknown-node")
        assert rec.status == TrustStatus.UNKNOWN
        assert not await service.is_trusted("unknown-node")

    @pytest.mark.asyncio
    async def test_grant_trust(self, service: TrustService) -> None:
        await service.initialize()
        await service.grant_trust("node-a", alias="Laptop")
        assert await service.is_trusted("node-a")
        rec = await service.get_record("node-a")
        assert rec.alias == "Laptop"
        assert rec.relationship == RelationshipType.PERSONAL

    @pytest.mark.asyncio
    async def test_revoke_trust(self, service: TrustService) -> None:
        await service.initialize()
        await service.grant_trust("node-b")
        await service.revoke_trust("node-b", reason="compromised")
        assert not await service.is_trusted("node-b")
        rec = await service.get_record("node-b")
        assert rec.status == TrustStatus.REVOKED
        assert rec.metadata.get("revoke_reason") == "compromised"

    @pytest.mark.asyncio
    async def test_re_grant_after_revoke(self, service: TrustService) -> None:
        await service.initialize()
        await service.grant_trust("node-c")
        await service.revoke_trust("node-c")
        await service.grant_trust("node-c")
        assert await service.is_trusted("node-c")

    @pytest.mark.asyncio
    async def test_list_records_filtered(self, service: TrustService) -> None:
        await service.initialize()
        await service.grant_trust("t1")
        await service.grant_trust("t2")
        await service.revoke_trust("r1")
        trusted = await service.list_records(status_filter=TrustStatus.TRUSTED)
        assert len(trusted) == 2
        revoked = await service.list_records(status_filter=TrustStatus.REVOKED)
        assert len(revoked) == 1

    @pytest.mark.asyncio
    async def test_persistence_across_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            svc1 = TrustService(data_dir=Path(tmp))
            await svc1.initialize()
            await svc1.grant_trust("persist-node", alias="Phone")
            # Simulate restart
            svc2 = TrustService(data_dir=Path(tmp))
            await svc2.initialize()
            assert await svc2.is_trusted("persist-node")
            rec = await svc2.get_record("persist-node")
            assert rec.alias == "Phone"

    @pytest.mark.asyncio
    async def test_events_emitted_on_grant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bus = EventBus()
            events_received: list = []

            async def handler(event: TrustGrantedEvent) -> None:
                events_received.append(event)

            await bus.subscribe(TrustGrantedEvent, handler)
            svc = TrustService(data_dir=Path(tmp), event_bus=bus)
            await svc.initialize()
            await svc.grant_trust("evt-node")
            assert len(events_received) == 1
            assert events_received[0].node_id == "evt-node"

    @pytest.mark.asyncio
    async def test_events_emitted_on_revoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bus = EventBus()
            events_received: list = []

            async def handler(event: TrustRevokedEvent) -> None:
                events_received.append(event)

            await bus.subscribe(TrustRevokedEvent, handler)
            svc = TrustService(data_dir=Path(tmp), event_bus=bus)
            await svc.initialize()
            await svc.grant_trust("evt-node")
            await svc.revoke_trust("evt-node", reason="test")
            assert len(events_received) == 1
            assert events_received[0].reason == "test"


class TestSecurityBoundary:
    """Ensure private material never leaks into trust records or events."""

    @pytest.mark.asyncio
    async def test_trust_record_contains_no_private_key(self) -> None:
        rec = TrustRecord(
            node_id="n1",
            public_key="dGVzdA==",
            status=TrustStatus.TRUSTED,
        )
        serialized = rec.model_dump_json()
        assert "private" not in serialized.lower()
        assert "dGVzdA==" in serialized  # public key IS present
