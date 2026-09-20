"""Shyam: Local-first, decentralized personal computing ecosystem and orchestration layer."""

from shyam.core.config import ShyamSettings
from shyam.core.lifecycle import LifecycleState
from shyam.core.runtime import ShyamRuntime
from shyam.events.bus import Event, EventBus
from shyam.providers.model import Provider
from shyam.providers.registry import ProviderRegistry

__version__ = "0.9.0"

__all__ = [
    "Event",
    "EventBus",
    "LifecycleState",
    "Provider",
    "ProviderRegistry",
    "ShyamRuntime",
    "ShyamSettings",
    "__version__",
]
