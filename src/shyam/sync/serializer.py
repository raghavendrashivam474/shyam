"""Deterministic canonical serialization for S14 sync payloads.

Ensures that any two identical logical data structures produce identical
byte representations across different Python runtimes, architecture bitness,
and dict insertion orders. This is essential for signature verification.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from shyam.sync.models import SyncEnvelope


def _normalize_value(val: Any) -> Any:
    """Recursively normalize data into deterministic JSON-serializable primitives."""
    if isinstance(val, BaseModel):
        return _normalize_value(val.model_dump(mode="python"))
    if isinstance(val, dict):
        return {str(k): _normalize_value(v) for k, v in sorted(val.items())}
    if isinstance(val, (list, tuple, set)):
        return [_normalize_value(item) for item in val]
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, UUID):
        return str(val)
    return val


def canonical_json_bytes(data: Any) -> bytes:
    """Serialize any Python/Pydantic object to deterministic canonical UTF-8 JSON bytes.

    Properties:
        - Sorted keys at all nesting levels
        - Minified separators (no arbitrary whitespace)
        - Preserves unicode characters as valid UTF-8
    """
    normalized = _normalize_value(data)
    json_str = json.dumps(
        normalized,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return json_str.encode("utf-8")


def get_signable_bytes(envelope: SyncEnvelope) -> bytes:
    """Extract and serialize the canonical bytes of an envelope for signing/verifying.

    The 'signature' field itself is explicitly excluded so that the envelope
    can be verified against the signature it carries.
    """
    data_dict = envelope.model_dump(mode="python", exclude={"signature"})
    return canonical_json_bytes(data_dict)
