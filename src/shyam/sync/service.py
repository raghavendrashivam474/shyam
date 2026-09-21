"""Peer State Synchronization Service — S14.

Coordinates local state observation packaging, cryptographic signing,
peer message ingestion, version vector causality checks, idempotency,
and non-destructive state convergence.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from shyam.sync.authenticator import SyncAuthenticator
from shyam.sync.events import SyncCompletedEvent, SyncRejectedEvent
from shyam.sync.models import (
    NodeVersionMap,
    SyncEnvelope,
    SyncOutcome,
    SyncPayload,
    SyncResult,
)
from shyam.sync.versions import VersionComparison, compare_versions, merge_version_maps

if TYPE_CHECKING:
    from shyam.events.bus import EventBus
    from shyam.identity.crypto import KeyPair
    from shyam.trust.service import TrustService

logger = logging.getLogger("shyam.sync.service")

_MAX_PROCESSED_MESSAGES = 1000


class SyncService:
    """Orchestrator for peer-to-peer state synchronization."""

    def __init__(
        self,
        local_node_id: UUID | str,
        keypair: KeyPair,
        trust_service: TrustService,
        event_bus: EventBus | None = None,
        max_tracked_messages: int = _MAX_PROCESSED_MESSAGES,
    ) -> None:
        self._local_node_id = str(local_node_id)
        self._keypair = keypair
        self._trust_service = trust_service
        self._event_bus = event_bus
        self._authenticator = SyncAuthenticator(trust_service=trust_service)

        self._lock = asyncio.Lock()
        # Fix: Initialize local version to 0 to represent "no local edits yet"
        self._version_map = NodeVersionMap(versions={self._local_node_id: 0})
        self._processed_message_ids: deque[str] = deque(maxlen=max_tracked_messages)

        # Synchronized ecosystem state facts (node_id -> set of capabilities / status)
        self._synced_capabilities: dict[str, set[str]] = {}
        self._synced_availability: dict[str, str] = {}

    @property
    def local_node_id(self) -> str:
        """String representation of the local node identifier."""
        return self._local_node_id

    @property
    def version_map(self) -> NodeVersionMap:
        """Current view of the local and remote version vectors."""
        return self._version_map

    async def increment_local_version(self) -> int:
        """Atomically bump the local node's version counter upon state mutation."""
        async with self._lock:
            current = self._version_map.get_version(self._local_node_id)
            new_v = current + 1
            self._version_map = self._version_map.with_update(self._local_node_id, new_v)
            return new_v

    async def update_local_facts(
        self,
        capabilities: dict[str, list[str]] | None = None,
        availability: dict[str, str] | None = None,
    ) -> None:
        """Ingest locally observed discovery facts and increment version."""
        async with self._lock:
            if capabilities:
                for n_id, caps in capabilities.items():
                    self._synced_capabilities.setdefault(n_id, set()).update(caps)
            if availability:
                self._synced_availability.update(availability)

            current = self._version_map.get_version(self._local_node_id)
            self._version_map = self._version_map.with_update(self._local_node_id, current + 1)

    async def create_sync_envelope(
        self,
        message_type: str = "sync_response",
    ) -> SyncEnvelope:
        """Construct and cryptographically sign an outgoing SyncEnvelope."""
        async with self._lock:
            payload = SyncPayload(
                known_node_ids=list(
                    set(self._version_map.versions.keys())
                    | set(self._synced_capabilities.keys())
                    | set(self._synced_availability.keys())
                ),
                node_capabilities={
                    n_id: sorted(list(caps))
                    for n_id, caps in self._synced_capabilities.items()
                },
                node_availability=dict(self._synced_availability),
            )

            envelope = SyncEnvelope(
                sender_node_id=self._local_node_id,
                sender_public_key=self._keypair.public_key_b64,
                message_type=message_type,
                version_map=self._version_map,
                payload=payload,
                message_id=str(uuid4()),
            )

            signed = self._authenticator.sign_envelope(envelope, self._keypair)
            return signed

    async def process_incoming_envelope(self, envelope: SyncEnvelope) -> SyncResult:
        """Authenticate, validate, and apply an incoming peer synchronization envelope.

        Guarantees:
            1. Unauthenticated / untrusted / revoked senders are rejected before state processing.
            2. Duplicate delivery is idempotent and produces no side effects.
            3. Self-sent messages or loop echoes are safely ignored.
            4. Vector clock evaluation prevents state regressions and detects concurrency.
            5. Component-wise union merging ensures deterministic state convergence.
        """
        sender_id = envelope.sender_node_id
        msg_id = envelope.message_id

        # Loop protection: ignore self-sent messages
        if sender_id == self._local_node_id:
            return SyncResult(
                outcome=SyncOutcome.ALREADY_CURRENT,
                sender_node_id=sender_id,
                message_id=msg_id,
                detail="Ignored self-originating envelope",
            )

        # 1. Authenticate cryptographically & check S13 trust
        valid, outcome, detail = await self._authenticator.authenticate_incoming(envelope)
        if not valid:
            logger.warning(
                "Sync rejected from node %s (msg: %s): %s",
                sender_id,
                msg_id,
                detail,
            )
            if self._event_bus:
                await self._event_bus.publish(
                    SyncRejectedEvent(
                        sender_node_id=sender_id,
                        message_id=msg_id,
                        outcome=outcome,
                        reason=detail,
                    )
                )
            return SyncResult(
                outcome=outcome,
                sender_node_id=sender_id,
                message_id=msg_id,
                detail=detail,
            )

        async with self._lock:
            # 2. Replay & Idempotency check
            if msg_id in self._processed_message_ids:
                return SyncResult(
                    outcome=SyncOutcome.ALREADY_CURRENT,
                    sender_node_id=sender_id,
                    message_id=msg_id,
                    detail="Duplicate message already processed",
                )

            v_before = self._version_map.get_version(self._local_node_id)

            # 3. Vector clock causality comparison
            comparison = compare_versions(self._version_map, envelope.version_map)

            if comparison in (VersionComparison.EQUAL, VersionComparison.AHEAD):
                # We already know everything the peer knows
                self._processed_message_ids.append(msg_id)
                return SyncResult(
                    outcome=SyncOutcome.ALREADY_CURRENT,
                    sender_node_id=sender_id,
                    message_id=msg_id,
                    local_version_before=v_before,
                    local_version_after=v_before,
                    detail=f"Local state is {comparison.value} relative to remote",
                )

            # 4. Merge incoming state facts non-destructively
            for n_id, caps in envelope.payload.node_capabilities.items():
                self._synced_capabilities.setdefault(n_id, set()).update(caps)

            for n_id, status in envelope.payload.node_availability.items():
                self._synced_availability[n_id] = status

            # 5. Merge version vectors component-wise
            self._version_map = merge_version_maps(self._version_map, envelope.version_map)
            self._processed_message_ids.append(msg_id)
            v_after = self._version_map.get_version(self._local_node_id)

            final_outcome = (
                SyncOutcome.CONFLICT
                if comparison == VersionComparison.CONCURRENT
                else SyncOutcome.APPLIED
            )

        logger.info(
            "State synchronized with peer %s (msg: %s, outcome: %s).",
            sender_id,
            msg_id,
            final_outcome,
        )

        if self._event_bus:
            await self._event_bus.publish(
                SyncCompletedEvent(
                    sender_node_id=sender_id,
                    message_id=msg_id,
                    outcome=final_outcome,
                )
            )

        return SyncResult(
            outcome=final_outcome,
            sender_node_id=sender_id,
            message_id=msg_id,
            local_version_before=v_before,
            local_version_after=v_after,
            detail=f"Synchronized facts successfully (causality: {comparison.value})",
        )

    async def get_node_capabilities(self, node_id: str) -> list[str]:
        """Return all known capabilities for a given node."""
        async with self._lock:
            return sorted(list(self._synced_capabilities.get(node_id, set())))

    async def get_node_availability(self, node_id: str) -> str | None:
        """Return the known availability status for a node."""
        async with self._lock:
            return self._synced_availability.get(node_id)
