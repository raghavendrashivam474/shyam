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
        description="Local directory for runtime state, logs, and artifacts.",
    )
    log_level: LogLevel = Field(
        default="INFO",
        description="Logging verbosity level.",
    )
    runtime_name: str = Field(
        default="shyam-core",
        description="Human-readable identifier for this runtime instance.",
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
        description="Interval in seconds between peer announcement broadcasts.",
    )
    discovery_expiry: float = Field(
        default=6.0,
        description="Heartbeat duration before a peer node is marked as lost.",
    )

    model_config = {
        "frozen": True,
        "arbitrary_types_allowed": True,
    }
