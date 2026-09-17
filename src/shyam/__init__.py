"""Shyam: Local-first, decentralized personal computing ecosystem and orchestration layer."""

from shyam.core.config import ShyamSettings
from shyam.core.lifecycle import LifecycleState
from shyam.core.runtime import ShyamRuntime
from shyam.events.bus import Event, EventBus

__version__ = "0.1.0"

__all__ = [
    "Event",
    "EventBus",
    "LifecycleState",
    "ShyamRuntime",
    "ShyamSettings",
    "__version__",
]
