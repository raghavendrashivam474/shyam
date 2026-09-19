"""Exceptions for the Shyam Provider subsystem."""


class ProviderError(Exception):
    """Base exception for provider-related errors."""


class DuplicateProviderError(ProviderError):
    """Raised when registering a provider that already exists."""


class ProviderNotFoundError(ProviderError):
    """Raised when an operation targets a provider that does not exist."""
