"""Unit tests for S13 cryptographic identity primitives."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from shyam.identity.crypto import (
    CryptoIdentity,
    KeyPair,
    load_or_create_keypair,
)


class TestKeyPairGeneration:
    """KeyPair creation and basic properties."""

    def test_generate_produces_valid_keypair(self) -> None:
        kp = KeyPair.generate()
        assert kp.public_key_b64
        assert len(kp.private_key_bytes) == 32

    def test_two_keypairs_are_distinct(self) -> None:
        kp1 = KeyPair.generate()
        kp2 = KeyPair.generate()
        assert kp1.public_key_b64 != kp2.public_key_b64
        assert kp1.private_key_bytes != kp2.private_key_bytes

    def test_from_private_bytes_roundtrip(self) -> None:
        kp = KeyPair.generate()
        restored = KeyPair.from_private_bytes(kp.private_key_bytes)
        assert restored.public_key_b64 == kp.public_key_b64


class TestSigningAndVerification:
    """Ed25519 sign/verify correctness."""

    def test_sign_and_verify_valid(self) -> None:
        kp = KeyPair.generate()
        data = b"hello shyam s13"
        sig = kp.sign(data)
        assert len(sig) == 64
        assert kp.verify(data, sig) is True

    def test_tampered_data_fails(self) -> None:
        kp = KeyPair.generate()
        sig = kp.sign(b"original")
        assert kp.verify(b"tampered", sig) is False

    def test_wrong_key_fails(self) -> None:
        kp1 = KeyPair.generate()
        kp2 = KeyPair.generate()
        sig = kp1.sign(b"data")
        assert kp2.verify(b"data", sig) is False

    def test_empty_data_signs(self) -> None:
        kp = KeyPair.generate()
        sig = kp.sign(b"")
        assert kp.verify(b"", sig) is True

    def test_large_payload(self) -> None:
        kp = KeyPair.generate()
        data = b"x" * 1_000_000
        sig = kp.sign(data)
        assert kp.verify(data, sig) is True


class TestStaticVerification:
    """KeyPair.verify_with_public_key using only the public key string."""

    def test_static_verify_valid(self) -> None:
        kp = KeyPair.generate()
        data = b"static test"
        sig = kp.sign(data)
        assert KeyPair.verify_with_public_key(kp.public_key_b64, data, sig) is True

    def test_static_verify_tampered(self) -> None:
        kp = KeyPair.generate()
        sig = kp.sign(b"real")
        assert KeyPair.verify_with_public_key(kp.public_key_b64, b"fake", sig) is False

    def test_static_verify_bad_key(self) -> None:
        kp1 = KeyPair.generate()
        kp2 = KeyPair.generate()
        sig = kp1.sign(b"data")
        assert KeyPair.verify_with_public_key(kp2.public_key_b64, b"data", sig) is False


class TestCryptoIdentityModel:
    """CryptoIdentity Pydantic model behavior."""

    def test_to_crypto_identity(self) -> None:
        kp = KeyPair.generate()
        nid = uuid4()
        cid = kp.to_crypto_identity(nid)
        assert cid.node_id == nid
        assert cid.algorithm == "Ed25519"
        assert cid.public_key == kp.public_key_b64

    def test_crypto_identity_is_frozen(self) -> None:
        kp = KeyPair.generate()
        cid = kp.to_crypto_identity(uuid4())
        with pytest.raises(Exception):
            cid.public_key = "hacked"  # type: ignore[misc]

    def test_crypto_identity_serialization(self) -> None:
        kp = KeyPair.generate()
        cid = kp.to_crypto_identity(uuid4())
        json_str = cid.model_dump_json()
        restored = CryptoIdentity.model_validate_json(json_str)
        assert restored.public_key == cid.public_key
        assert restored.node_id == cid.node_id


class TestCryptoPersistence:
    """load_or_create_keypair disk round-trip."""

    def test_create_and_reload(self) -> None:
        nid = uuid4()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            kp1, cid1 = load_or_create_keypair(data_dir, nid)
            kp2, cid2 = load_or_create_keypair(data_dir, nid)
            assert cid1.public_key == cid2.public_key
            assert kp1.private_key_bytes == kp2.private_key_bytes

    def test_persistence_survives_restart(self) -> None:
        nid = uuid4()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            kp1, _ = load_or_create_keypair(data_dir, nid)
            sig = kp1.sign(b"persistent")
            # Simulate restart
            kp2, _ = load_or_create_keypair(data_dir, nid)
            assert kp2.verify(b"persistent", sig) is True

    def test_private_key_not_in_public_json(self) -> None:
        nid = uuid4()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            load_or_create_keypair(data_dir, nid)
            public_json = (data_dir / "crypto" / "public.json").read_text()
            assert "private" not in public_json.lower()
