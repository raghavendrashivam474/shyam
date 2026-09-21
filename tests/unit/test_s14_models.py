"""Unit tests for S14 synchronization domain models."""

import pytest
from shyam.sync.models import (
    SYNC_PROTOCOL_VERSION,
    NodeVersionMap,
    SyncEnvelope,
    SyncOutcome,
    SyncPayload,
    SyncResult,
)


class TestNodeVersionMap:
    """Tests for per-node version vector."""

    def test_empty_map(self):
        vm = NodeVersionMap()
        assert vm.versions == {}
        assert vm.get_version("any-node") == 0

    def test_get_version_existing(self):
        vm = NodeVersionMap(versions={"node-A": 5})
        assert vm.get_version("node-A") == 5

    def test_with_update_creates_new_map(self):
        vm1 = NodeVersionMap(versions={"node-A": 5})
        vm2 = vm1.with_update("node-B", 3)

        # Original unchanged (frozen)
        assert vm1.get_version("node-B") == 0
        # New map has both
        assert vm2.get_version("node-A") == 5
        assert vm2.get_version("node-B") == 3

    def test_with_update_overwrites(self):
        vm1 = NodeVersionMap(versions={"node-A": 5})
        vm2 = vm1.with_update("node-A", 10)
        assert vm2.get_version("node-A") == 10
        assert vm1.get_version("node-A") == 5  # original untouched


class TestSyncPayload:
    """Tests for the state facts payload."""

    def test_empty_payload(self):
        p = SyncPayload()
        assert p.known_node_ids == []
        assert p.node_capabilities == {}
        assert p.node_availability == {}
        assert p.extra == {}

    def test_frozen(self):
        p = SyncPayload(known_node_ids=["A"])
        with pytest.raises(Exception):
            p.known_node_ids = ["B"]  # type: ignore[misc]


class TestSyncEnvelope:
    """Tests for the wire envelope."""

    def _make_envelope(self, **overrides) -> SyncEnvelope:
        defaults = dict(
            sender_node_id="node-A",
            sender_public_key="dGVzdA==",
            message_type="sync_response",
            version_map=NodeVersionMap(versions={"node-A": 1}),
            payload=SyncPayload(),
            message_id="msg-001",
        )
        defaults.update(overrides)
        return SyncEnvelope(**defaults)

    def test_protocol_version_default(self):
        env = self._make_envelope()
        assert env.protocol_version == SYNC_PROTOCOL_VERSION

    def test_unsigned_by_default(self):
        env = self._make_envelope()
        assert env.is_signed() is False
        assert env.signature == ""

    def test_signed_when_signature_present(self):
        env = self._make_envelope(signature="c2lnbmF0dXJl")
        assert env.is_signed() is True

    def test_frozen(self):
        env = self._make_envelope()
        with pytest.raises(Exception):
            env.sender_node_id = "node-B"  # type: ignore[misc]


class TestSyncResult:
    """Tests for local sync outcome."""

    def test_applied_result(self):
        r = SyncResult(
            outcome=SyncOutcome.APPLIED,
            sender_node_id="node-A",
            message_id="msg-001",
            local_version_before=5,
            local_version_after=6,
        )
        assert r.outcome == SyncOutcome.APPLIED
        assert r.local_version_after > r.local_version_before

    def test_rejected_result(self):
        r = SyncResult(
            outcome=SyncOutcome.REJECTED_UNTRUSTED,
            sender_node_id="unknown-node",
            detail="Node not in trust store",
        )
        assert r.outcome == SyncOutcome.REJECTED_UNTRUSTED
