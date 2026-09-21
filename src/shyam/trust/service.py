"""Trust Service for Shyam — S13.

Coordinates trust management, query operations, and policy persistence.
Publishes domain events when trust states are granted, updated, or revoked.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Sequence

from shyam.events.bus import EventBus
from shyam.trust.models import (
    RelationshipType,
    TrustGrantedEvent,
    TrustRecord,
    TrustRevokedEvent,
    TrustStatus,
    TrustUpdatedEvent,
)
from shyam.trust.store import TrustStore

logger = logging.getLogger("shyam.trust.service")


class TrustService:
    """Manages local trust policy, persistence, and event emissions for Shyam."""

    def __init__(
        self,
        data_dir: Path,
        event_bus: EventBus | None = None,
        store: TrustStore | None = None,
    ) -> None:
        self._data_dir = data_dir
        self._event_bus = event_bus
        self._store = store or TrustStore(data_dir=data_dir)
        self._records: dict[str, TrustRecord] = {}
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Load persisted trust state from disk into memory."""
        async with self._lock:
            if self._initialized:
                return
            self._records = self._store.load()
            self._initialized = True
            logger.info("Initialized TrustService with %d records.", len(self._records))

    async def get_record(self, node_id: str) -> TrustRecord:
        """Retrieve the trust record for a node. Returns an UNKNOWN record if not found."""
        async with self._lock:
            if not self._initialized:
                self._records = self._store.load()
                self._initialized = True
            return self._records.get(node_id, TrustRecord(node_id=node_id, status=TrustStatus.UNKNOWN))

    async def is_trusted(self, node_id: str) -> bool:
        """Return True only if the node explicitly has status TRUSTED."""
        rec = await self.get_record(node_id)
        return rec.is_trusted

    async def grant_trust(
        self,
        node_id: str,
        public_key: str | None = None,
        relationship: RelationshipType = RelationshipType.PERSONAL,
        alias: str = "",
        metadata: dict | None = None,
    ) -> TrustRecord:
        """Explicitly mark a node as TRUSTED, persist, and publish event."""
        async with self._lock:
            existing = self._records.get(node_id)
            if existing is None:
                record = TrustRecord(
                    node_id=node_id,
                    public_key=public_key,
                    status=TrustStatus.TRUSTED,
                    relationship=relationship,
                    alias=alias,
                    metadata=metadata or {},
                )
            else:
                record = existing.with_status(
                    status=TrustStatus.TRUSTED,
                    relationship=relationship,
                    alias=alias or existing.alias,
                    public_key=public_key or existing.public_key,
                    metadata=metadata if metadata is not None else existing.metadata,
                )

            self._records[node_id] = record
            self._store.save(self._records)
            logger.info("Granted trust to node %s (relationship=%s)", node_id, relationship)

        if self._event_bus:
            await self._event_bus.publish(
                TrustGrantedEvent(
                    node_id=node_id,
                    public_key=record.public_key,
                    relationship=record.relationship,
                    alias=record.alias,
                )
            )

        return record

    async def revoke_trust(
        self,
        node_id: str,
        reason: str | None = None,
    ) -> TrustRecord:
        """Explicitly revoke trust from a node, mark as REVOKED, persist, and emit event."""
        async with self._lock:
            existing = self._records.get(node_id)
            if existing is None:
                record = TrustRecord(
                    node_id=node_id,
                    status=TrustStatus.REVOKED,
                    metadata={"revoke_reason": reason} if reason else {},
                )
            else:
                meta = dict(existing.metadata)
                if reason:
                    meta["revoke_reason"] = reason
                record = existing.with_status(
                    status=TrustStatus.REVOKED,
                    metadata=meta,
                )

            self._records[node_id] = record
            self._store.save(self._records)
            logger.info("Revoked trust from node %s (reason=%s)", node_id, reason)

        if self._event_bus:
            await self._event_bus.publish(
                TrustRevokedEvent(
                    node_id=node_id,
                    reason=reason,
                )
            )

        return record

    async def list_records(
        self,
        status_filter: TrustStatus | None = None,
    ) -> Sequence[TrustRecord]:
        """List all managed trust records, optionally filtered by status."""
        async with self._lock:
            if not self._initialized:
                self._records = self._store.load()
                self._initialized = True

            if status_filter is None:
                return tuple(self._records.values())
            return tuple(r for r in self._records.values() if r.status == status_filter)

    async def get_trusted_node_ids(self) -> set[str]:
        """Return a set of all node IDs that are currently TRUSTED."""
        records = await self.list_records(status_filter=TrustStatus.TRUSTED)
        return {r.node_id for r in records}
