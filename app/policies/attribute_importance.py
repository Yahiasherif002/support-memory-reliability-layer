"""Salience weights for context budgeting."""

from __future__ import annotations

from app.policies.attributes import Attr

DEFAULT_IMPORTANCE = 0.5

ATTRIBUTE_IMPORTANCE: dict[str, float] = {
    Attr.ACCOUNT_STATUS: 1.0,
    Attr.PLAN_TIER: 0.95,
    Attr.SUPPORT_TIER: 0.9,
    Attr.SLA_TARGET: 0.85,
    Attr.SEATS: 0.8,
    Attr.CONTACT_PREFERENCE: 0.8,
    Attr.RENEWAL_DATE: 0.75,
    Attr.TICKET_STATUS: 0.7,
    Attr.POLICY_RULE: 0.7,
    Attr.EMAIL: 0.6,
    Attr.REGION: 0.5,
    Attr.SEGMENT: 0.5,
    Attr.NAME: 0.5,
    Attr.LAST_CONTACT_REASON: 0.5,
}


def importance(attribute: str) -> float:
    return ATTRIBUTE_IMPORTANCE.get(attribute, DEFAULT_IMPORTANCE)
