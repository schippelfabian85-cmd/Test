"""Domain-Events über die Outbox (Kernel §8).

Publizieren schreibt in derselben Transaktion wie die Fachänderung einen
Outbox-Eintrag; ein Worker stellt mindestens einmal zu (K-11: Events
transportieren nur IDs und wenige Kennzahlen).
"""

import json
from collections import defaultdict
from typing import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from kernel.modelle import OutboxEvent, jetzt_utc

_konsumenten: dict[str, list[Callable]] = defaultdict(list)


def publiziere(session: Session, event_type: str, tenant_id: UUID,
               actor_id: UUID | None, payload: dict) -> OutboxEvent:
    event = OutboxEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        actor_id=actor_id,
        payload_json=json.dumps(payload, default=str, ensure_ascii=False),
    )
    session.add(event)
    return event


def registriere_konsument(event_type: str, handler: Callable) -> None:
    """Konsumenten müssen idempotent sein (At-least-once-Zustellung)."""
    _konsumenten[event_type].append(handler)


def verarbeite_outbox(session: Session) -> int:
    """Stellt offene Events zu und markiert sie. Rückgabe: Anzahl zugestellt."""
    offene = session.scalars(
        select(OutboxEvent).where(OutboxEvent.versendet_am.is_(None))
        .order_by(OutboxEvent.occurred_at)
    ).all()
    for event in offene:
        for handler in _konsumenten.get(event.event_type, []):
            handler(session, event.tenant_id, json.loads(event.payload_json))
        event.versendet_am = jetzt_utc()
    return len(offene)
