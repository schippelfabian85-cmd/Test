"""Idempotente Schreibendpunkte (Kernel §9): Wiederholung mit demselben
`Idempotency-Key` liefert dasselbe Ergebnis, ohne die Aktion zu wiederholen."""

import json
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from kernel.auth import AuthKontext
from kernel.modelle import IdempotenzEintrag


def mit_idempotenz(session: Session, ktx: AuthKontext, schluessel: str | None,
                   endpunkt: str, aktion: Callable[[], tuple[int, dict]]) -> tuple[int, dict]:
    """Führt `aktion` aus oder liefert die gespeicherte Antwort des Erstaufrufs."""
    if not schluessel:
        return aktion()
    vorhanden = session.scalars(select(IdempotenzEintrag).where(
        IdempotenzEintrag.tenant_id == ktx.tenant_id,
        IdempotenzEintrag.schluessel == schluessel,
        IdempotenzEintrag.endpunkt == endpunkt,
    )).first()
    if vorhanden is not None:
        return vorhanden.status_code, json.loads(vorhanden.antwort_json)
    status, antwort = aktion()
    session.add(IdempotenzEintrag(
        tenant_id=ktx.tenant_id, schluessel=schluessel, endpunkt=endpunkt,
        status_code=status, antwort_json=json.dumps(antwort, default=str,
                                                    ensure_ascii=False),
    ))
    return status, antwort
