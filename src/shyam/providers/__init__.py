"""Shyam Providers subsystem - S4.

Provides formal provider modeling and local in-memory registry.
"""

from shyam.providers.events import (
    ProviderRegisteredEvent,
    ProviderUnregisteredEvent,
    ProviderUpdatedEvent,
)
from shyam.providers.exceptions import (
    DuplicateProviderError,
    ProviderError,
    ProviderNotFoundError,
)
from shyam.providers.model import Provider
from shyam.providers.registry import ProviderRegistry

__all__ = [
    "DuplicateProviderError",
    "Provider",
    "ProviderError",
    "ProviderNotFoundError",
    "ProviderRegistry",
    "ProviderRegisteredEvent",
    "ProviderUnregisteredEvent",
    "ProviderUpdatedEvent",
]
