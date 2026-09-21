"""Cryptographic signing and trust validation boundary for S14.

Integrates S13 Identity and Trust subsystems into the sync pipeline.
Guarantees that unauthenticated, untrusted, or revoked nodes cannot
inject state facts into the local ecosystem.
"""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING

from shyam.identity.crypto import KeyPair
from shyam.sync.models import (
    SYNC_PROTOCOL_VERSION,
    SyncEnvelope,
    SyncOutcome,
)
from shyam.sync.serializer import get_signable_bytes

if TYPE_CHECKING:
    from shyam.trust.service import TrustService

logger = logging.getLogger("shyam.sync.authenticator")


class SyncAuthenticator:
    """Authentication gatekeeper for peer synchronization messages."""

    def __init__(self, trust_service: TrustService) -> None:
        self._trust_service = trust_service

    def sign_envelope(self, envelope: SyncEnvelope, keypair: KeyPair) -> SyncEnvelope:
        """Deterministically sign an outgoing SyncEnvelope with local Ed25519 KeyPair."""
        signable = get_signable_bytes(envelope)
        raw_sig = keypair.sign(signable)
        b64_sig = base64.b64encode(raw_sig).decode("ascii")
        return envelope.model_copy(update={"signature": b64_sig})

    async def authenticate_incoming(self, envelope: SyncEnvelope) -> tuple[bool, SyncOutcome, str]:
        """Validate, identify, check trust, and verify Ed25519 signature of an envelope.

        Returns:
            tuple[bool, SyncOutcome, str]: (is_valid, outcome_enum, detail_message)
        """
        # 1. Protocol compatibility check
        if envelope.protocol_version != SYNC_PROTOCOL_VERSION:
            return (
                False,
                SyncOutcome.REJECTED_PROTOCOL_MISMATCH,
                f"Unsupported protocol version '{envelope.protocol_version}', expected '{SYNC_PROTOCOL_VERSION}'",
            )

        # 2. Signature presence
        if not envelope.signature:
            return (
                False,
                SyncOutcome.REJECTED_INVALID_SIGNATURE,
                "Envelope is unsigned",
            )

        sender_id = envelope.sender_node_id
        if not sender_id:
            return (
                False,
                SyncOutcome.REJECTED_MALFORMED,
                "Envelope missing sender_node_id",
            )

        # 3. Lookup sender in S13 Trust Store
        record = await self._trust_service.get_record(sender_id)

        if record.is_revoked:
            return (
                False,
                SyncOutcome.REJECTED_REVOKED,
                f"Node '{sender_id}' trust standing is REVOKED",
            )

        if not record.is_trusted:
            return (
                False,
                SyncOutcome.REJECTED_UNTRUSTED,
                f"Node '{sender_id}' is not in local trust store",
            )

        # 4. Public key consistency verification
        pinned_key = record.public_key
        if pinned_key and pinned_key != envelope.sender_public_key:
            return (
                False,
                SyncOutcome.REJECTED_INVALID_SIGNATURE,
                f"Envelope public key does not match pinned trust key for node '{sender_id}'",
            )

        key_to_verify = pinned_key or envelope.sender_public_key
        if not key_to_verify:
            return (
                False,
                SyncOutcome.REJECTED_MALFORMED,
                f"No public key available for node '{sender_id}'",
            )

        # 5. Cryptographic signature verification over canonical bytes
        try:
            raw_sig = base64.b64decode(envelope.signature)
            signable_bytes = get_signable_bytes(envelope)
            is_valid = KeyPair.verify_with_public_key(
                public_key_b64=key_to_verify,
                data=signable_bytes,
                signature=raw_sig,
            )
        except Exception as exc:
            return (
                False,
                SyncOutcome.REJECTED_INVALID_SIGNATURE,
                f"Signature parsing or verification error: {exc}",
            )

        if not is_valid:
            return (
                False,
                SyncOutcome.REJECTED_INVALID_SIGNATURE,
                "Ed25519 signature verification failed",
            )

        return (True, SyncOutcome.APPLIED, "Authentication successful")
