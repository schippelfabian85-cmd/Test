"""Audit-Protokoll (K-4): jede fachlich relevante Änderung schreibt einen Eintrag."""

import json

from sqlalchemy.orm import Session

from kernel.auth import AuthKontext
from kernel.modelle import AuditLog


def schreibe_audit(session: Session, ktx: AuthKontext, modul: str, entitaet: str,
                   entitaet_id, aktion: str,
                   alt: dict | None = None, neu: dict | None = None) -> None:
    session.add(AuditLog(
        tenant_id=ktx.tenant_id,
        benutzer_id=ktx.benutzer_id,
        modul=modul,
        entitaet=entitaet,
        entitaet_id=str(entitaet_id),
        aktion=aktion,
        alt_json=json.dumps(alt, default=str, ensure_ascii=False) if alt is not None else None,
        neu_json=json.dumps(neu, default=str, ensure_ascii=False) if neu is not None else None,
    ))
