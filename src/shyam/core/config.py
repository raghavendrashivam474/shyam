"""Runtime configuration and settings for Shyam."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
Environment = Literal["development", "testing", "production", "local"]


class ShyamSettings(BaseModel):
    """Runtime configuration settings for the Shyam core runtime."""

    environment: Environment = Field(
        default="local",
        description="Execution environment tier.",
    )
    data_directory: Path = Field(
        default=Path.home() / ".shyam",
        description="Local directory for runtime state and logs.",
    )
    log_level: LogLevel = Field(
        default="INFO",
        description="Logging verbosity level.",
    )
    runtime_name: str = Field(
        default="shyam-core",
        description="Human-readable identifier for this runtime.",
    )

    # Local Peer Discovery S2 Settings
    discovery_enabled: bool = Field(
        default=True,
        description="Whether to enable local UDP peer discovery.",
    )
    discovery_port: int = Field(
        default=54321,
        description="Port for UDP local peer discovery broadcasts.",
    )
    discovery_interval: float = Field(
        default=2.0,
        description="Interval in seconds between peer broadcasts.",
    )
    discovery_expiry: float = Field(
        default=6.0,
        description="Heartbeat duration before a peer is lost.",
    )

    # Zarya EIP-1 Integration S6 Settings
    zarya_enabled: bool = Field(
        default=True,
        description="Attempt connection to local Zarya agent.",
    )
    zarya_url: str = Field(
        default="http://127.0.0.1:8765/ecosystem/v1",
        description="EIP-1 base URL for Zarya ecosystem endpoint.",
    )
    zarya_token: str | None = Field(
        default=None,
        description=(
            "Auth token for Zarya EIP-1. "
            "Falls back to ZARYA_ECOSYSTEM_TOKEN env var."
        ),
    )

    model_config = {
        "frozen": True,
        "arbitrary_types_allowed": True,
    }
