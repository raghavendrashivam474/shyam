"""Logging setup and utilities for Shyam."""

import logging
import sys

from shyam.core.config import ShyamSettings


def setup_logging(settings: ShyamSettings) -> logging.Logger:
    """Configure structured logging for the Shyam namespace based on settings."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger = logging.getLogger("shyam")
    logger.setLevel(log_level)

    # Avoid duplicate handlers on re-initialization
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
