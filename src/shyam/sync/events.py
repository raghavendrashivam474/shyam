"""Domain events for S14 Peer Synchronization."""

from __future__ import annotations

from shyam.events.bus import Event
from shyam.sync.models import SyncOutcome


class SyncCompletedEvent(Event):
    """Emitted when a state synchronization envelope is successfully verified and applied."""

    sender_node_id: str
    message_id: str
    outcome: SyncOutcome


class SyncRejectedEvent(Event):
    """Emitted when an incoming sync envelope is rejected by security or protocol guards."""

    sender_node_id: str
    message_id: str
    outcome: SyncOutcome
    reason: str
