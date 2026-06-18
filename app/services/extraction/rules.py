"""Deterministic fact extraction from payload + free text, keyed by source.

No ``event_type``. Extraction branches on ``entity_type`` and reads payload
(authoritative) then text (regex/keywords). An event flagged as a correction or
supersession gets a resolution precedence bump. The registry maps every ``source``
to ``RuleExtractor`` — the pluggable seam (a future LLM extractor for chat/email
would implement the same interface).

Extraction targets demonstrated on the assignment data: plans, support tiers, SLA
targets, contact preferences, account preferences, regions/segments, ticket status,
seats (incl. the 42→48 correction), policies, contact email/phone (identity
ambiguity), and correction/duplicate indicators.
"""

from __future__ import annotations

import re
from typing import Any

from app.db.models import RawEvent
from app.domain.enums import EntityType, Source
from app.domain.facts import ExtractedFact
from app.policies.attributes import Attr

PLAN_WORDS = ["enterprise", "professional", "business", "growth", "premium", "starter", "scale", "pro", "free"]
STATUS_WORDS = ["active", "suspended", "closed", "churned", "cancelled", "trial"]
TICKET_WORDS = ["in progress", "in_progress", "escalated", "reopened", "resolved", "pending", "open", "closed"]
CHANNEL_KEYS = ("contact_preference", "preferred_channel", "channel", "preference")
CORRECTION_HINTS = ("correction", "corrected", "actually", "should be", "instead", "supersede", "mistake", "typo")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SEATS_RE = re.compile(r"(\d+)\s*(?:affected\s+)?(?:seats?|users?|user count)", re.I)
SLA_RE = re.compile(r"(\d+)\s*(business hours|business days|hours?|hrs?|days?)", re.I)
SUPPORT_RE = re.compile(r"\b(enterprise|premium|standard|starter|basic|pro)\s+support\b", re.I)


def _is_correction(event: RawEvent) -> bool:
    p = event.payload or {}
    if p.get("correction") is True or p.get("supersedes") or p.get("supersede"):
        return True
    text = (event.text or "").lower()
    return any(h in text for h in CORRECTION_HINTS)


def _labelled(text: str, label: str) -> str | None:
    m = re.search(rf"{label}\s*[:=]\s*([A-Za-z][\w\- ]*)", text or "", re.I)
    return m.group(1).strip() if m else None


def _channel(text: str, payload: dict, use_text: bool) -> str | None:
    for key in CHANNEL_KEYS:
        if payload.get(key):
            return str(payload[key]).strip().lower().replace(" ", "_")
    if not use_text:
        return None
    t = (text or "").lower()
    if "whatsapp" in t:
        return "whatsapp"
    if "email only" in t or "email-only" in t or "only email" in t:
        return "email_only"
    if "sms" in t:
        return "sms"
    if re.search(r"\bemail\b", t):
        return "email"
    if "phone" in t or "call" in t:
        return "phone"
    return None


def _plan(text: str, payload: dict) -> str | None:
    if payload.get("plan"):
        return str(payload["plan"]).strip()  # preserve casing, e.g. "Enterprise Support"
    for word in PLAN_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", text, re.I):
            return word.capitalize()
    return None


def _phone(text: str, payload: dict) -> str | None:
    raw = payload.get("phone")
    if not raw:
        return None
    return "".join(ch for ch in str(raw) if ch.isdigit() or ch == "+")


class RuleExtractor:
    name = "rule-extractor"
    version = "1.0"

    def extract(self, event: RawEvent) -> list[ExtractedFact]:
        et = event.entity_type
        if et == EntityType.POLICY:
            return self._policy(event)
        if et == EntityType.TICKET:
            return self._ticket(event)
        if et == EntityType.CONTACT:
            return self._contact(event)
        return self._account(event)

    def _account(self, event: RawEvent) -> list[ExtractedFact]:
        p, text = event.payload or {}, event.text or ""
        out: list[ExtractedFact] = []

        if (plan := _plan(text, p)):
            out.append(self._fact(event, Attr.PLAN_TIER, plan, "plan/text"))

        support = p.get("support_tier") or p.get("support_plan")
        if not support and (m := SUPPORT_RE.search(text)):
            support = m.group(1).capitalize()
        if support:
            out.append(self._fact(event, Attr.SUPPORT_TIER, str(support).strip(), "support_tier/text"))

        sla = None
        if p.get("sla") or p.get("sla_hours"):
            sla = p.get("sla") or {"value": p.get("sla_hours"), "unit": "hours"}
        elif p.get("p1_response_hours") is not None:
            sla = {"priority": "P1", "value": p["p1_response_hours"], "unit": "hours"}
        elif p.get("standard_response"):
            sla = {"priority": "standard", "target": p["standard_response"]}
        elif "sla" in text.lower() and (m := SLA_RE.search(text)):
            sla = {"value": int(m.group(1)), "unit": m.group(2).lower()}
        if sla is not None:
            out.append(self._fact(event, Attr.SLA_TARGET, sla, "sla/text"))

        # Account-level priority/preference (NOT a contact channel).
        if p.get("preference"):
            out.append(self._fact(event, Attr.ACCOUNT_PREFERENCE, str(p["preference"]), "preference"))

        region = p.get("region") or _labelled(text, "region")
        if region:
            out.append(self._fact(event, Attr.REGION, str(region).strip(), "region/text"))
        segment = p.get("segment") or _labelled(text, "segment")
        if segment:
            out.append(self._fact(event, Attr.SEGMENT, str(segment).strip(), "segment/text"))

        status = p.get("status")
        if status is None:
            for w in STATUS_WORDS:
                if re.search(rf"\b{re.escape(w)}\b", text, re.I):
                    status = w
                    break
        if status:
            out.append(self._fact(event, Attr.ACCOUNT_STATUS, str(status).lower(), "status/text"))
        if p.get("renewal_date"):
            out.append(self._fact(event, Attr.RENEWAL_DATE, p["renewal_date"], "renewal_date"))
        return out

    def _contact(self, event: RawEvent) -> list[ExtractedFact]:
        p, text = event.payload or {}, event.text or ""
        out: list[ExtractedFact] = []
        email = p.get("email") or (m.group(0) if (m := EMAIL_RE.search(text)) else None)
        if email:
            out.append(self._fact(event, Attr.EMAIL, str(email).strip().lower(), "email/text"))
        if (phone := _phone(text, p)):
            out.append(self._fact(event, Attr.PHONE, phone, "phone"))
        name = p.get("name") or p.get("contact_name")
        if name:
            out.append(self._fact(event, Attr.NAME, str(name).strip(), "name"))
        if (channel := _channel(text, p, use_text=True)):
            out.append(self._fact(event, Attr.CONTACT_PREFERENCE, channel, "preference/text"))
        return out

    def _ticket(self, event: RawEvent) -> list[ExtractedFact]:
        p, text = event.payload or {}, event.text or ""
        out: list[ExtractedFact] = []
        status = p.get("status")
        if status is None:
            for w in TICKET_WORDS:
                if w in text.lower():
                    status = w.replace(" ", "_")
                    break
        if status:
            value: dict[str, Any] = {"status": str(status).lower()}
            out.append(self._fact(event, Attr.TICKET_STATUS, value, "status/text"))

        seats = p.get("affected_seats")
        if seats is None:
            seats = p.get("seats")
        if seats is None and (m := SEATS_RE.search(text)):
            seats = int(m.group(1))
        if seats is not None:
            out.append(self._fact(event, Attr.SEATS, int(seats), "affected_seats/text"))

        reason = p.get("reason") or p.get("subject") or p.get("topic") or p.get("symptom")
        if reason:
            out.append(self._fact(event, Attr.LAST_CONTACT_REASON, str(reason), "reason"))
        return out

    def _policy(self, event: RawEvent) -> list[ExtractedFact]:
        p, text = event.payload or {}, event.text or ""
        rule = {
            "name": p.get("policy_name") or p.get("name") or "policy",
            "rule": p.get("rule") or p.get("policy") or text,
            "scope_account_id": p.get("scope_account_id"),
        }
        return [self._fact(event, Attr.POLICY_RULE, rule, "policy/text")]

    def _fact(self, event: RawEvent, attribute: str, value: Any, field: str) -> ExtractedFact:
        return ExtractedFact(attribute=attribute, value=value, confidence=None,
                             is_correction=_is_correction(event), locator={"field": field})


class ExtractorRegistry:
    def __init__(self) -> None:
        self._by_source: dict[str, RuleExtractor] = {}

    def register(self, source: str, extractor: RuleExtractor) -> None:
        self._by_source[source] = extractor

    def get(self, source: str) -> RuleExtractor | None:
        return self._by_source.get(source)


def default_registry() -> ExtractorRegistry:
    registry = ExtractorRegistry()
    shared = RuleExtractor()
    for source in Source:
        registry.register(source, shared)
    return registry
