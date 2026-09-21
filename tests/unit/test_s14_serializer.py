"""Unit tests for S14 canonical serializer."""

from datetime import UTC, datetime
from uuid import UUID

from shyam.sync.models import NodeVersionMap, SyncEnvelope, SyncPayload
from shyam.sync.serializer import canonical_json_bytes, get_signable_bytes


def test_canonical_dict_ordering():
    d1 = {"b": 2, "a": 1, "c": {"y": 20, "x": 10}}
    d2 = {"c": {"x": 10, "y": 20}, "a": 1, "b": 2}
    assert canonical_json_bytes(d1) == canonical_json_bytes(d2)


def test_signable_bytes_ignores_signature():
    ts = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)
    env1 = SyncEnvelope(
        sender_node_id="node-1",
        sender_public_key="key-1",
        message_type="sync_request",
        version_map=NodeVersionMap(versions={"node-1": 1}),
        payload=SyncPayload(known_node_ids=["node-1"]),
        message_id="msg-1",
        timestamp=ts,
        signature="",
    )
    env2 = env1.model_copy(update={"signature": "some_signature_base64"})

    bytes1 = get_signable_bytes(env1)
    bytes2 = get_signable_bytes(env2)

    assert bytes1 == bytes2
    assert b"signature" not in bytes1


def test_canonical_handles_uuid_and_datetime():
    uid = UUID("12345678-1234-5678-1234-567812345678")
    dt = datetime(2026, 9, 21, 10, 0, 0, tzinfo=UTC)
    payload = {"id": uid, "time": dt}
    raw = canonical_json_bytes(payload)
    assert raw == b'{"id":"12345678-1234-5678-1234-567812345678","time":"2026-09-21T10:00:00+00:00"}'
