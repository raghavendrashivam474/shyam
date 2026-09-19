"""Unit tests for Node Identity models and IdentityManager."""

from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from shyam.identity import (
    IdentityCorruptionError,
    IdentityManager,
    NodeIdentity,
)


def test_node_identity_model_instantiation() -> None:
    """Test standard model creation and default values."""
    ident = NodeIdentity(node_name="alpha-node")
    assert isinstance(ident.node_id, UUID)
    assert ident.node_name == "alpha-node"
    assert ident.protocol_version == "0.2.0"
    assert ident.created_at is not None


def test_node_identity_immutability() -> None:
    """NodeIdentity must be frozen and immutable."""
    ident = NodeIdentity(node_name="alpha-node")
    with pytest.raises(ValidationError):
        ident.node_name = "beta-node"  # type: ignore[misc]


def test_identity_manager_first_initialization(tmp_path: Path) -> None:
    """First run generates and saves a new identity to disk."""
    manager = IdentityManager(data_dir=tmp_path, custom_node_name="test-node-1")
    ident = manager.get_or_create_identity()

    assert ident.node_name == "test-node-1"
    assert isinstance(ident.node_id, UUID)
    assert manager.identity_file_path.exists()
    assert manager.identity == ident


def test_identity_manager_subsequent_initialization(tmp_path: Path) -> None:
    """Subsequent managers pointing to same data_dir load the exact same identity."""
    manager1 = IdentityManager(data_dir=tmp_path, custom_node_name="node-primary")
    ident1 = manager1.get_or_create_identity()

    manager2 = IdentityManager(data_dir=tmp_path, custom_node_name="different-name-ignored")
    ident2 = manager2.get_or_create_identity()

    assert ident1.node_id == ident2.node_id
    assert ident1.node_name == ident2.node_name
    assert ident1.created_at == ident2.created_at
    assert ident2.node_name == "node-primary"


def test_identity_manager_corrupted_json(tmp_path: Path) -> None:
    """Corrupted JSON file raises IdentityCorruptionError without silently overwriting."""
    identity_dir = tmp_path / "identity"
    identity_dir.mkdir(parents=True, exist_ok=True)
    bad_file = identity_dir / "node.json"
    bad_file.write_text("{ this is not valid json :", encoding="utf-8")

    manager = IdentityManager(data_dir=tmp_path)
    with pytest.raises(IdentityCorruptionError) as exc_info:
        manager.get_or_create_identity()

    assert "Corrupted node identity file" in str(exc_info.value)


def test_identity_manager_invalid_schema(tmp_path: Path) -> None:
    """Valid JSON with invalid schema raises IdentityCorruptionError."""
    identity_dir = tmp_path / "identity"
    identity_dir.mkdir(parents=True, exist_ok=True)
    bad_file = identity_dir / "node.json"
    bad_file.write_text('{"node_id": "not-a-uuid", "node_name": 123}', encoding="utf-8")

    manager = IdentityManager(data_dir=tmp_path)
    with pytest.raises(IdentityCorruptionError) as exc_info:
        manager.get_or_create_identity()

    assert "Validation failed" in str(exc_info.value)
