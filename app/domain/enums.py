"""Controlled vocabularies — aligned to the assignment's Memory Event schema.

There is intentionally **no** ``event_type``: the assignment events don't carry
one. Extraction is keyed on ``source`` and reads ``text`` + ``payload``.
"""

from __future__ import annotations

from enum import StrEnum


class Source(StrEnum):
    CRM = "crm"
    CONTRACT = "contract"
    CHAT = "chat"
    EMAIL = "email"
    AGENT_NOTE = "agent_note"
    SYSTEM = "system"


class EntityType(StrEnum):
    ACCOUNT = "account"
    CONTACT = "contact"
    TICKET = "ticket"
    POLICY = "policy"


class Reliability(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Polarity(StrEnum):
    ASSERT = "assert"
    RETRACT = "retract"


class DedupStatus(StrEnum):
    NEW = "new"
    DUPLICATE_REPLAY = "duplicate_replay"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"


class ContradictionKind(StrEnum):
    BELIEF_VALUE_CONFLICT = "belief_value_conflict"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    IDENTITY_AMBIGUITY = "identity_ambiguity"


class ContradictionStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    AUTO_CLOSED = "auto_closed"


class IdentityStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    CONFIRMED_SAME = "confirmed_same"
    CONFIRMED_DISTINCT = "confirmed_distinct"


class ProcessingStatus(StrEnum):
    EXTRACTED = "extracted"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    CONFLICT = "conflict"
    ERROR = "error"
