"""Nummernkreise (Kernel §2/§3): fachliche, sichtbare Nummern."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from kernel.modelle import Nummernkreis


def naechste_nummer(session: Session, tenant_id: UUID, code: str,
                    praefix: str = "", breite: int = 5) -> str:
    kreis = session.scalars(
        select(Nummernkreis)
        .where(Nummernkreis.tenant_id == tenant_id, Nummernkreis.code == code)
        .with_for_update()
    ).first()
    if kreis is None:
        kreis = Nummernkreis(tenant_id=tenant_id, code=code, praefix=praefix,
                             naechster_wert=1)
        session.add(kreis)
        session.flush()
    wert = kreis.naechster_wert
    kreis.naechster_wert = wert + 1
    return f"{kreis.praefix}{wert:0{breite}d}"
