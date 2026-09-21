"""Peer Synchronization subsystem — S14.

Provides local-first, peer-to-peer state synchronization between
trusted Shyam nodes. Consumes S12 (ecosystem state), S13 (identity
and trust), and Flux (connectivity) without replacing any of them.
"""

from shyam.sync.authenticator import SyncAuthenticator
from shyam.sync.events import SyncCompletedEvent, SyncRejectedEvent
from shyam.sync.models import (
    SYNC_PROTOCOL_VERSION,
    NodeVersionMap,
    SyncEnvelope,
    SyncOutcome,
    SyncPayload,
    SyncResult,
)
from shyam.sync.serializer import canonical_json_bytes, get_signable_bytes
from shyam.sync.service import SyncService
from shyam.sync.versions import VersionComparison, compare_versions, merge_version_maps

__all__ = [
    "SYNC_PROTOCOL_VERSION",
    "NodeVersionMap",
    "SyncAuthenticator",
    "SyncCompletedEvent",
    "SyncEnvelope",
    "SyncOutcome",
    "SyncPayload",
    "SyncRejectedEvent",
    "SyncResult",
    "SyncService",
    "VersionComparison",
    "canonical_json_bytes",
    "compare_versions",
    "get_signable_bytes",
    "merge_version_maps",
]
