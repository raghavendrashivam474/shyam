"""Shyam Capabilities subsystem - S3.

Provides formal capability modeling and local in-memory registry.
"""

from shyam.capabilities.events import (
    CapabilityRegisteredEvent,
    CapabilityUnregisteredEvent,
    CapabilityUpdatedEvent,
)
from shyam.capabilities.exceptions import (
    CapabilityError,
    CapabilityNotFoundError,
    DuplicateCapabilityError,
)
from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.capabilities.registry import CapabilityRegistry

__all__ = [
    "AvailabilityStatus",
    "Capability",
    "CapabilityError",
    "CapabilityNotFoundError",
    "CapabilityRegistry",
    "CapabilityRegisteredEvent",
    "CapabilityUnregisteredEvent",
    "CapabilityUpdatedEvent",
    "DuplicateCapabilityError",
]
