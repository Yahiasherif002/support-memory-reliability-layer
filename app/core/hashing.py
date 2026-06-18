"""Canonical hashing.

Determinism is the backbone of idempotency, content de-duplication, and stable
fact identity. ``canonical_json`` produces a byte-for-byte stable representation
(sorted keys, tight separators) so the same logical payload always hashes to the
same digest regardless of key order or incidental whitespace.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Stable JSON: sorted keys, no incidental whitespace.

    ``default=str`` lets us hash datetimes and other simple objects without the
    caller having to pre-serialize them.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def sha256_hex(value: Any) -> str:
    """SHA-256 of the canonical JSON form of ``value``."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
