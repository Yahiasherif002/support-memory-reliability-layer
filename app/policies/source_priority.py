"""Source authority — the tiebreaker *after* reliability.

A signed **contract** is the strongest source, then the **crm** system-of-record,
then **system** integrations, **agent_note**, inbound **email**, casual **chat**.
"""

from __future__ import annotations

from app.domain.enums import Source

SOURCE_AUTHORITY: dict[str, int] = {
    Source.CONTRACT: 100,
    Source.CRM: 80,
    Source.SYSTEM: 70,
    Source.AGENT_NOTE: 50,
    Source.EMAIL: 30,
    Source.CHAT: 20,
}

DEFAULT_AUTHORITY = 0


def authority(source: str) -> int:
    return SOURCE_AUTHORITY.get(source, DEFAULT_AUTHORITY)
