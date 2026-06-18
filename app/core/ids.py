"""Identifier generation.

Opaque, prefixed UUIDs make IDs self-describing in logs and API responses
(``fact_3f2a...``) without leaking ordering or volume information.
"""

from __future__ import annotations

import uuid

from app.core.hashing import sha256_hex


def new_id(prefix: str = "") -> str:
    raw = uuid.uuid4().hex
    return f"{prefix}_{raw}" if prefix else raw


def deterministic_id(prefix: str, *parts: object) -> str:
    """A content-addressed id derived from a natural key.

    Every derived row (entity, identifier, fact, evidence, belief, contradiction,
    candidate) uses one of these so that re-deriving state from the immutable raw
    log reproduces *byte-identical* ids — the precondition for a clean rebuild and
    deterministic replay. Raw events keep random ``new_id`` ids: they are the log,
    not a projection.
    """
    return f"{prefix}_{sha256_hex(list(parts))[:32]}"
