"""Exceptions for the Shyam Capability subsystem."""


class CapabilityError(Exception):
    """Base exception for capability-related errors."""


class DuplicateCapabilityError(CapabilityError):
    """Raised when registering a capability that already exists."""


class CapabilityNotFoundError(CapabilityError):
    """Raised when an operation targets a capability that does not exist."""
