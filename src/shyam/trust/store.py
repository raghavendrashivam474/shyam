"""Persistent Trust Store for Shyam — S13.

Provides thread-safe atomic local persistence for node trust records.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from shyam.trust.models import TrustRecord

logger = logging.getLogger("shyam.trust.store")

_DEFAULT_TRUST_FILE = "trust_store.json"


class TrustStoreError(Exception):
    """Base exception for trust store failures."""


class TrustStoreCorruptionError(TrustStoreError):
    """Raised when trust store file is corrupt or unparseable."""


class TrustStore:
    """Atomic local file persistence for trust records."""

    def __init__(self, data_dir: Path, filename: str = _DEFAULT_TRUST_FILE) -> None:
        self._data_dir = data_dir
        self._store_file = data_dir / filename

    def load(self) -> dict[str, TrustRecord]:
        """Load all trust records from disk. Returns empty dict if no store file exists."""
        if not self._store_file.exists():
            return {}

        try:
            raw_text = self._store_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise TrustStoreError(f"Failed to read trust store at '{self._store_file}': {exc}") from exc

        if not raw_text.strip():
            return {}

        try:
            data = json.loads(raw_text)
            if not isinstance(data, dict):
                raise TrustStoreCorruptionError(f"Trust store content is not a JSON object: {data}")
            return {node_id: TrustRecord.model_validate(rec) for node_id, rec in data.items()}
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise TrustStoreCorruptionError(
                f"Corrupted trust store file at '{self._store_file}': {exc}"
            ) from exc

    def save(self, records: dict[str, TrustRecord]) -> None:
        """Atomically persist trust records dictionary to disk."""
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            temp_file = self._store_file.with_suffix(".tmp")
            payload = {
                node_id: record.model_dump(mode="json")
                for node_id, record in records.items()
            }
            temp_file.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            temp_file.replace(self._store_file)
        except OSError as exc:
            raise TrustStoreError(f"Failed to persist trust store to '{self._store_file}': {exc}") from exc
