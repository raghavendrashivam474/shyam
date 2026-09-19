"""Shyam Capability Model - S3.

Defines the formal representation of what a Shyam node can provide.
A capability describes an *ability*, not an implementation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AvailabilityStatus(StrEnum):
    """Whether a capability is currently available."""

    REGISTERED = "registered"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class Capability(BaseModel):
    """A formal description of what a Shyam node can do.

    A capability describes an *ability* - not who provides it,
    where it runs, or how it is executed.

    Capability != Provider != Node != Execution
    """

    model_config = {"frozen": True}

    capability_id: str = Field(
        ...,
        description="Stable, namespaced identifier (e.g. 'file.read')",
    )
    name: str = Field(
        ...,
        description="Human-readable name for this capability",
    )
    version: str = Field(
        default="1.0.0",
        description="Semantic version string (e.g. '1.0.0')",
    )
    description: str = Field(
        default="",
        description="What this capability does",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible metadata about this capability",
    )
    availability: AvailabilityStatus = Field(
        default=AvailabilityStatus.REGISTERED,
        description="Current availability status",
    )

    @field_validator("capability_id")
    @classmethod
    def validate_capability_id(cls, v: str) -> str:
        """Capability IDs must be namespaced dot-separated identifiers."""
        if not v or "." not in v:
            raise ValueError(f"Capability ID must be namespaced (e.g. 'file.read'), got: '{v}'")
        parts = v.split(".")
        if any(not part.isidentifier() for part in parts):
            raise ValueError(f"Capability ID parts must be valid identifiers, got: '{v}'")
        return v

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Version must be 1-3 dot-separated non-negative integers."""
        parts = v.split(".")
        if len(parts) < 1 or len(parts) > 3:
            raise ValueError(f"Version must be 1-3 dot-separated integers, got: '{v}'")
        for part in parts:
            if not part.isdigit():
                raise ValueError(f"Version parts must be non-negative integers, got: '{v}'")
        return v
