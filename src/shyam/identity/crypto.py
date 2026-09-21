"""Cryptographic identity primitives for Shyam nodes — S13.

Provides Ed25519 keypair generation, signing, and verification.
The private key is handled exclusively through the KeyPair handle
and is never embedded in serializable Pydantic models.

Architectural contract:
    - CryptoIdentity (public) may be shared across the ecosystem.
    - KeyPair (private) never leaves local storage.
    - The logical NodeIdentity.node_id remains the primary ecosystem
      identifier; CryptoIdentity references it but does not replace it.
"""

from __future__ import annotations

import base64
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("shyam.identity.crypto")


# ---------------------------------------------------------------------------
# Public crypto identity model (safe to serialize / share)
# ---------------------------------------------------------------------------

class CryptoIdentity(BaseModel):
    """Public cryptographic identity bound to a logical Shyam node.

    This model contains only public material and is safe to include
    in ecosystem snapshots, discovery payloads, and trust records.
    """

    model_config = ConfigDict(frozen=True)

    node_id: UUID = Field(
        description="Logical node ID this crypto identity belongs to.",
    )
    public_key: str = Field(
        description="Base64-encoded Ed25519 public key (raw 32 bytes).",
    )
    algorithm: str = Field(
        default="Ed25519",
        description="Signing algorithm identifier.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this keypair was first generated.",
    )


# ---------------------------------------------------------------------------
# In-memory keypair handle (private material stays here only)
# ---------------------------------------------------------------------------

class KeyPair:
    """In-memory Ed25519 keypair handle.

    The private key is intentionally NOT a Pydantic field and is
    never serialized through model_dump / model_dump_json.
    """

    __slots__ = ("_private", "_public")

    def __init__(
        self,
        private_key: Ed25519PrivateKey,
        public_key: Ed25519PublicKey,
    ) -> None:
        self._private = private_key
        self._public = public_key

    # -- factory ----------------------------------------------------------

    @classmethod
    def generate(cls) -> KeyPair:
        """Generate a fresh Ed25519 keypair."""
        private = Ed25519PrivateKey.generate()
        return cls(private_key=private, public_key=private.public_key())

    @classmethod
    def from_private_bytes(cls, raw: bytes) -> KeyPair:
        """Reconstruct a keypair from raw 32-byte private key seed."""
        private = Ed25519PrivateKey.from_private_bytes(raw)
        return cls(private_key=private, public_key=private.public_key())

    # -- signing / verification -------------------------------------------

    def sign(self, data: bytes) -> bytes:
        """Sign arbitrary data. Returns the 64-byte Ed25519 signature."""
        return self._private.sign(data)

    def verify(self, data: bytes, signature: bytes) -> bool:
        """Verify a signature against this keypair's public key.

        Returns True if valid, False otherwise (never raises on bad sig).
        """
        try:
            self._public.verify(signature, data)
            return True
        except Exception:
            return False

    @staticmethod
    def verify_with_public_key(
        public_key_b64: str,
        data: bytes,
        signature: bytes,
    ) -> bool:
        """Verify a signature using a base64-encoded public key.

        Useful when you only have a CryptoIdentity, not a full KeyPair.
        """
        try:
            raw = base64.b64decode(public_key_b64)
            pub = Ed25519PublicKey.from_public_bytes(raw)
            pub.verify(signature, data)
            return True
        except Exception:
            return False

    # -- serialization helpers (public only) ------------------------------

    @property
    def public_key_b64(self) -> str:
        """Base64-encoded raw 32-byte public key."""
        raw = self._public.public_bytes_raw()
        return base64.b64encode(raw).decode("ascii")

    @property
    def private_key_bytes(self) -> bytes:
        """Raw 32-byte private key seed. Handle with extreme care."""
        return self._private.private_bytes_raw()

    def to_crypto_identity(self, node_id: UUID) -> CryptoIdentity:
        """Derive the shareable public CryptoIdentity from this keypair."""
        return CryptoIdentity(
            node_id=node_id,
            public_key=self.public_key_b64,
        )


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

_CRYPTO_DIR_NAME = "crypto"
_PUBLIC_FILE = "public.json"
_PRIVATE_FILE = "private.key"


def load_or_create_keypair(
    data_dir: Path,
    node_id: UUID,
) -> tuple[KeyPair, CryptoIdentity]:
    """Load an existing keypair from disk or generate and persist a new one.

    Storage layout::

        <data_dir>/crypto/
            public.json      ← CryptoIdentity (public, safe to share)
            private.key      ← raw 32-byte Ed25519 seed (LOCAL ONLY)

    Returns:
        (KeyPair, CryptoIdentity) — the in-memory handle and its public model.
    """
    crypto_dir = data_dir / _CRYPTO_DIR_NAME
    public_path = crypto_dir / _PUBLIC_FILE
    private_path = crypto_dir / _PRIVATE_FILE

    # --- attempt to load existing ----------------------------------------
    if public_path.exists() and private_path.exists():
        try:
            raw_private = private_path.read_bytes()
            kp = KeyPair.from_private_bytes(raw_private)
            crypto_id = CryptoIdentity.model_validate_json(
                public_path.read_text(encoding="utf-8"),
            )
            # Guard: if node_id changed (shouldn't happen), regenerate.
            if crypto_id.node_id != node_id:
                logger.warning(
                    "Crypto identity node_id mismatch (%s vs %s). Regenerating.",
                    crypto_id.node_id,
                    node_id,
                )
            else:
                logger.info("Loaded existing crypto identity for node %s.", node_id)
                return kp, crypto_id
        except Exception:
            logger.exception("Failed to load crypto identity. Regenerating.")

    # --- generate fresh --------------------------------------------------
    logger.info("Generating new Ed25519 keypair for node %s.", node_id)
    kp = KeyPair.generate()
    crypto_id = kp.to_crypto_identity(node_id)

    crypto_dir.mkdir(parents=True, exist_ok=True)

    # Atomic-ish write for public identity
    tmp_pub = public_path.with_suffix(".tmp")
    tmp_pub.write_text(crypto_id.model_dump_json(indent=2), encoding="utf-8")
    tmp_pub.replace(public_path)

    # Private key — raw bytes, no encoding overhead
    tmp_priv = private_path.with_suffix(".tmp")
    tmp_priv.write_bytes(kp.private_key_bytes)
    tmp_priv.replace(private_path)

    logger.info("Crypto identity persisted to %s.", crypto_dir)
    return kp, crypto_id
