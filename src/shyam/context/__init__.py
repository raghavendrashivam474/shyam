"""Ecosystem State and Context subsystem - S12.

Provides a unified, in-memory view of what is currently happening
in the Shyam ecosystem by aggregating S8 discovery and S10 workflow events.
"""

from shyam.context.models import (
    ActiveWorkItem,
    ActivityKind,
    EcosystemContext,
    EcosystemState,
    RecentActivityEntry,
    WorkStatus,
)
from shyam.context.store import EcosystemStateStore

__all__ = [
    "ActiveWorkItem",
    "ActivityKind",
    "EcosystemContext",
    "EcosystemState",
    "EcosystemStateStore",
    "RecentActivityEntry",
    "WorkStatus",
]
