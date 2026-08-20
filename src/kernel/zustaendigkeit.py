"""ZustaendigkeitPort (Kernel §7, bereitgestellt von M00).

K-8: Berechtigungsprüfung ist zweistufig — Rolle und Sichtbarkeitsbereich.
ADMIN/PLANER/CONTROLLER sehen alles (None = uneingeschränkt), EL/OL sehen
die ihnen zugewiesenen Objekte/Personen, MA nur sich selbst.
"""

from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from kernel.auth import AuthKontext
from kernel.modelle import Zustaendigkeit

ALLSICHT_ROLLEN = {"ADMIN", "PLANER", "CONTROLLER"}


class ZustaendigkeitPortV1(Protocol):
    def sichtbare_objekte(self, ktx: AuthKontext) -> set[UUID] | None: ...
    def sichtbare_personen(self, ktx: AuthKontext) -> set[UUID] | None: ...


class ZustaendigkeitDienst:
    def __init__(self, session: Session):
        self._session = session

    def _eintraege(self, ktx: AuthKontext) -> list[Zustaendigkeit]:
        return list(self._session.scalars(
            select(Zustaendigkeit).where(
                Zustaendigkeit.tenant_id == ktx.tenant_id,
                Zustaendigkeit.benutzer_id == ktx.benutzer_id,
            )
        ))

    def sichtbare_objekte(self, ktx: AuthKontext) -> set[UUID] | None:
        if ktx.hat_rolle(*ALLSICHT_ROLLEN):
            return None
        return {z.objekt_id for z in self._eintraege(ktx) if z.objekt_id is not None}

    def sichtbare_personen(self, ktx: AuthKontext) -> set[UUID] | None:
        if ktx.hat_rolle(*ALLSICHT_ROLLEN):
            return None
        return {z.mitarbeiter_id for z in self._eintraege(ktx)
                if z.mitarbeiter_id is not None}
