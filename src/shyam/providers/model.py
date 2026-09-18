"""Shyam Provider Model - S4.

Defines the formal representation of who/how provides a capability.
A provider describes metadata and capability association, not execution.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from shyam.capabilities.model import AvailabilityStatus


class Provider(BaseModel):
    """A formal description of who/how provides capabilities.

    A provider describes *who* provides a set of abilities and *how* they are grouped,
    but not where they run, or how they are executed.

    Capability != Provider != Node != Execution
    """

    model_config = {"frozen": True}

    provider_id: str = Field(
        ...,
        description="Stable, namespaced identifier (e.g. 'local.filesystem')",
    )
    name: str = Field(
        ...,
        description="Human-readable name for this provider",
    )
    version: str = Field(
        default="1.0.0",
        description="Semantic version string (e.g. '1.0.0')",
    )
    description: str = Field(
        default="",
        description="What this provider provides",
    )
    capabilities: tuple[str, ...] = Field(
        default_factory=tuple,
        description="IDs of capabilities provided by this provider",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible metadata about this provider",
    )
    availability: AvailabilityStatus = Field(
        default=AvailabilityStatus.REGISTERED,
        description="Current availability status",
    )

    @field_validator("provider_id")
    @classmethod
    def validate_provider_id(cls, v: str) -> str:
        """Provider IDs must be namespaced dot-separated identifiers."""
        if not v or "." not in v:
            raise ValueError(
                f"Provider ID must be namespaced (e.g. 'local.filesystem'), got: '{v}'"
            )
        parts = v.split(".")
        if any(not part.isidentifier() for part in parts):
            raise ValueError(
                f"Provider ID parts must be valid identifiers, got: '{v}'"
            )
        return v

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Version must be 1-3 dot-separated non-negative integers."""
        parts = v.split(".")
        if len(parts) < 1 or len(parts) > 3:
            raise ValueError(
                f"Version must be 1-3 dot-separated integers, got: '{v}'"
            )
        for part in parts:
            if not part.isdigit():
                raise ValueError(
                    f"Version parts must be non-negative integers, got: '{v}'"
                )
        return v
