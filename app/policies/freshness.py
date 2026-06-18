"""Staleness policy: per-attribute freshness windows."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.policies.attributes import Attr

DEFAULT_TTL = timedelta(days=365)

ATTRIBUTE_TTL: dict[str, timedelta] = {
    Attr.PLAN_TIER: timedelta(days=400),
    Attr.SUPPORT_TIER: timedelta(days=400),
    Attr.SEATS: timedelta(days=400),
    Attr.SLA_TARGET: timedelta(days=400),
    Attr.CONTACT_PREFERENCE: timedelta(days=180),
    Attr.REGION: timedelta(days=1500),
    Attr.SEGMENT: timedelta(days=1500),
    Attr.ACCOUNT_STATUS: timedelta(days=120),
    Attr.TICKET_STATUS: timedelta(days=30),
    Attr.POLICY_RULE: timedelta(days=1500),
    Attr.RENEWAL_DATE: timedelta(days=400),
    Attr.EMAIL: timedelta(days=365),
    Attr.NAME: timedelta(days=1500),
    Attr.LAST_CONTACT_REASON: timedelta(days=60),
}


def ttl_for(attribute: str) -> timedelta:
    return ATTRIBUTE_TTL.get(attribute, DEFAULT_TTL)


def is_stale(attribute: str, observed_at: datetime, reference_time: datetime) -> bool:
    return (reference_time - observed_at) > ttl_for(attribute)
