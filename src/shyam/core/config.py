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

    model_config = {
        "frozen": True,
        "arbitrary_types_allowed": True,
    }
