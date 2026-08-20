"""Idempotency contract and deterministic key generation (§13, DS-A35)."""

import hashlib
import json
from typing import Any, Dict


def generate_activity_idempotency_key(
    execution_id: str, node_id: str, input_data: Dict[str, Any], revision: int = 1
) -> str:
    """Computes a deterministic idempotency digest for an activity execution."""
    canonical_json = json.dumps(input_data, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:16]
    return f"{execution_id}:{node_id}:r{revision}:{digest}"


def compute_content_id(content: bytes) -> str:
    """Computes content addressable BLAKE3 or SHA-256 hash for raw payloads."""
    return hashlib.sha256(content).hexdigest()
