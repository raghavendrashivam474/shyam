"""Node identity persistence and lifecycle manager."""

import json
import logging
import socket
from pathlib import Path

from pydantic import ValidationError

from shyam.identity.model import NodeIdentity

logger = logging.getLogger("shyam.identity.manager")


class IdentityError(Exception):
    """Base exception for identity management errors."""


class IdentityCorruptionError(IdentityError):
    """Raised when an existing identity file cannot be parsed or validated."""


class IdentityManager:
    """Manages persistent NodeIdentity creation, loading, and validation."""

    def __init__(self, data_dir: Path, custom_node_name: str | None = None) -> None:
        self._data_dir = Path(data_dir)
        self._identity_dir = self._data_dir / "identity"
        self._identity_file = self._identity_dir / "node.json"
        self._custom_node_name = custom_node_name
        self._identity: NodeIdentity | None = None

    @property
    def identity(self) -> NodeIdentity | None:
        """Returns the loaded or generated node identity, or None if not initialized."""
        return self._identity

    @property
    def identity_file_path(self) -> Path:
        """Returns the path to the node identity JSON file."""
        return self._identity_file

    def get_or_create_identity(self) -> NodeIdentity:
        """Loads existing identity or generates and persists a new one.

        Raises:
            IdentityCorruptionError: If the persisted identity file is corrupted or invalid.
            IdentityError: If file I/O operations fail.
        """
        if self._identity is not None:
            return self._identity

        if self._identity_file.exists():
            self._identity = self._load_identity()
            logger.info(
                "Loaded persistent node identity: %s (%s)",
                self._identity.node_name,
                self._identity.node_id,
            )
        else:
            self._identity = self._create_and_persist_identity()
            logger.info(
                "Created new persistent node identity: %s (%s)",
                self._identity.node_name,
                self._identity.node_id,
            )

        return self._identity

    def _load_identity(self) -> NodeIdentity:
        try:
            raw_text = self._identity_file.read_text(encoding="utf-8")
        except OSError as e:
            raise IdentityError(
                f"Failed to read identity file at '{self._identity_file}': {e}"
            ) from e

        try:
            data = json.loads(raw_text)
            return NodeIdentity.model_validate(data)
        except (json.JSONDecodeError, ValidationError, TypeError) as e:
            raise IdentityCorruptionError(
                f"Corrupted node identity file at '{self._identity_file}'. "
                f"Validation failed with error: {e}"
            ) from e

    def _create_and_persist_identity(self) -> NodeIdentity:
        name = self._custom_node_name or socket.gethostname() or "shyam-node"
        identity = NodeIdentity(node_name=name)

        try:
            self._identity_dir.mkdir(parents=True, exist_ok=True)
            temp_file = self._identity_file.with_suffix(".tmp")
            temp_file.write_text(identity.model_dump_json(indent=2), encoding="utf-8")
            temp_file.replace(self._identity_file)
        except OSError as e:
            raise IdentityError(
                f"Failed to persist identity file at '{self._identity_file}': {e}"
            ) from e

        return identity
