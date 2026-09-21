"""Composite capabilities subsystem - S11.

Provides reusable composition of existing capabilities through
the S10 WorkflowEngine.
"""

from shyam.composite.engine import CompositeEngine
from shyam.composite.errors import (
    CompositeBindingError,
    CompositeDefinitionError,
    CompositeError,
    CompositeInputError,
    CompositeNotFoundError,
)
from shyam.composite.models import (
    Binding,
    BindingSource,
    CompositeCapability,
    CompositeResult,
    CompositeStep,
)
from shyam.composite.registry import CompositeCapabilityRegistry

__all__ = [
    "Binding",
    "BindingSource",
    "CompositeBindingError",
    "CompositeCapability",
    "CompositeCapabilityRegistry",
    "CompositeDefinitionError",
    "CompositeEngine",
    "CompositeError",
    "CompositeInputError",
    "CompositeNotFoundError",
    "CompositeResult",
    "CompositeStep",
]
