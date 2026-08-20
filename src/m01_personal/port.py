"""MitarbeiterPortV1 (M01 §3) — echte Implementierung und Stub (K-2)."""

from dataclasses import dataclass, replace
from datetime import date
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from kernel.auth import AuthKontext
from kernel.dtos import VertragsgrenzenDTO
from m01_personal import service
from m01_personal.modelle import Mitarbeiter


@dataclass(frozen=True)
class MitarbeiterDTO:
    id: UUID
    tenant_id: UUID
    personalnummer: str
    nachname: str
    vorname: str
    geburtsdatum: date
    status: str
    eintrittsdatum: date
    austrittsdatum: date | None
    funktion_codes: tuple[str, ...]
    kostenstelle_nummer: str | None


class MitarbeiterPortV1(Protocol):
    def mitarbeiter(self, id: UUID) -> MitarbeiterDTO | None: ...
    def suche(self, tenant_id: UUID, status: str | None = None,
              funktion_code: str | None = None) -> list[MitarbeiterDTO]: ...
    def vertragsgrenzen(self, mitarbeiter_id: UUID, stichtag: date) -> VertragsgrenzenDTO: ...
    def ist_aktiv(self, mitarbeiter_id: UUID, stichtag: date) -> bool: ...


class MitarbeiterPort:
    def __init__(self, session: Session, ktx: AuthKontext):
        self._session = session
        self._ktx = ktx

    def _dto(self, ma: Mitarbeiter) -> MitarbeiterDTO:
        from m01_personal.modelle import Kostenstelle
        nummer = None
        if ma.kostenstelle_id is not None:
            ks = self._session.get(Kostenstelle, ma.kostenstelle_id)
            nummer = ks.nummer if ks else None
        return MitarbeiterDTO(
            id=ma.id, tenant_id=ma.tenant_id, personalnummer=ma.personalnummer,
            nachname=ma.nachname, vorname=ma.vorname, geburtsdatum=ma.geburtsdatum,
            status=ma.status, eintrittsdatum=ma.eintrittsdatum,
            austrittsdatum=ma.austrittsdatum,
            funktion_codes=service.funktion_codes(self._session, ma.id),
            kostenstelle_nummer=nummer,
        )

    def mitarbeiter(self, id: UUID) -> MitarbeiterDTO | None:
        ma = self._session.get(Mitarbeiter, id)
        if ma is None or ma.tenant_id != self._ktx.tenant_id:
            return None
        return self._dto(ma)

    def suche(self, tenant_id: UUID, status: str | None = None,
              funktion_code: str | None = None) -> list[MitarbeiterDTO]:
        treffer = service.suche(self._session, self._ktx, status=status,
                                funktion_code=funktion_code)
        return [self._dto(m) for m in treffer]

    def vertragsgrenzen(self, mitarbeiter_id: UUID, stichtag: date) -> VertragsgrenzenDTO:
        return service.vertragsgrenzen(self._session, self._ktx, mitarbeiter_id, stichtag)

    def ist_aktiv(self, mitarbeiter_id: UUID, stichtag: date) -> bool:
        return service.ist_aktiv(self._session, self._ktx, mitarbeiter_id, stichtag)
