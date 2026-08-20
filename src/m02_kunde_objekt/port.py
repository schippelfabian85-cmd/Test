"""ObjektPortV1 und KundePortV1 (M02 §3) samt DTOs und Stub-Bausteinen."""

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from kernel.auth import AuthKontext
from m02_kunde_objekt import service
from m02_kunde_objekt.modelle import Kunde, Objekt, ObjektMitarbeiter, ObjektZuschlag


@dataclass(frozen=True)
class ObjektDTO:
    id: UUID
    tenant_id: UUID
    objektnummer: str
    bezeichnung: str
    kunde_id: UUID
    objektart_code: str
    bundesland: str
    latitude: float | None
    longitude: float | None
    geofence_radius_meter: int
    einsatzbeginn: date
    einsatzende: date | None
    aktiv: bool
    kostenstelle_nummer: str | None


@dataclass(frozen=True)
class ZuschlagDTO:
    id: UUID
    bezeichnung: str
    art: str          # PROZENT | BETRAG
    wert: int


@dataclass(frozen=True)
class RechnungsdatenDTO:
    kunde_id: UUID
    firmenname: str
    zahlungsziel_tage: int
    skonto_prozent: int
    skonto_tage: int
    rechnungsversand: str
    rechnung_verdichtung: str
    leitweg_id: str | None
    rechnungsempfaenger_email: str | None


@dataclass(frozen=True)
class KundeDTO:
    id: UUID
    tenant_id: UUID
    kundennummer: str
    firmenname: str
    aktiv: bool


class ObjektPortV1(Protocol):
    def objekt(self, id: UUID) -> ObjektDTO | None: ...
    def objekte_kunde(self, kunde_id: UUID) -> list[ObjektDTO]: ...
    def ist_freigegeben(self, objekt_id: UUID, mitarbeiter_id: UUID,
                        stichtag: date) -> bool: ...
    def stammkraefte(self, objekt_id: UUID) -> list[UUID]: ...
    def zuschlaege(self, objekt_id: UUID, stichtag: date) -> list[ZuschlagDTO]: ...


class KundePortV1(Protocol):
    def kunde(self, id: UUID) -> KundeDTO | None: ...
    def rechnungsdaten(self, kunde_id: UUID) -> RechnungsdatenDTO: ...


def _objekt_dto(session: Session, objekt: Objekt) -> ObjektDTO:
    from m01_personal.modelle import Kostenstelle
    from m02_kunde_objekt.modelle import Objektart
    art_code = ""
    if objekt.objektart_id is not None:
        art = session.get(Objektart, objekt.objektart_id)
        art_code = art.code if art else ""
    ks_nummer = None
    if objekt.kostenstelle_id is not None:
        ks = session.get(Kostenstelle, objekt.kostenstelle_id)
        ks_nummer = ks.nummer if ks else None
    return ObjektDTO(
        id=objekt.id, tenant_id=objekt.tenant_id, objektnummer=objekt.objektnummer,
        bezeichnung=objekt.bezeichnung, kunde_id=objekt.kunde_id,
        objektart_code=art_code, bundesland=objekt.bundesland,
        latitude=objekt.latitude, longitude=objekt.longitude,
        geofence_radius_meter=objekt.geofence_radius_meter,
        einsatzbeginn=objekt.einsatzbeginn, einsatzende=objekt.einsatzende,
        aktiv=objekt.aktiv, kostenstelle_nummer=ks_nummer,
    )


class ObjektPort:
    def __init__(self, session: Session, ktx: AuthKontext):
        self._session = session
        self._ktx = ktx

    def objekt(self, id: UUID) -> ObjektDTO | None:
        objekt = self._session.get(Objekt, id)
        if objekt is None or objekt.tenant_id != self._ktx.tenant_id:
            return None
        return _objekt_dto(self._session, objekt)

    def objekte_kunde(self, kunde_id: UUID) -> list[ObjektDTO]:
        objekte = self._session.scalars(select(Objekt).where(
            Objekt.tenant_id == self._ktx.tenant_id, Objekt.kunde_id == kunde_id,
        ).order_by(Objekt.objektnummer)).all()
        return [_objekt_dto(self._session, o) for o in objekte]

    def ist_freigegeben(self, objekt_id: UUID, mitarbeiter_id: UUID,
                        stichtag: date) -> bool:
        return service.ist_freigegeben(self._session, objekt_id, mitarbeiter_id, stichtag)

    def stammkraefte(self, objekt_id: UUID) -> list[UUID]:
        zeilen = self._session.scalars(select(ObjektMitarbeiter).where(
            ObjektMitarbeiter.objekt_id == objekt_id,
            ObjektMitarbeiter.ist_stammkraft.is_(True),
        )).all()
        return [z.mitarbeiter_id for z in zeilen]

    def zuschlaege(self, objekt_id: UUID, stichtag: date) -> list[ZuschlagDTO]:
        zeilen = self._session.scalars(select(ObjektZuschlag).where(
            ObjektZuschlag.objekt_id == objekt_id,
            ObjektZuschlag.gueltig_ab <= stichtag,
            (ObjektZuschlag.gueltig_bis.is_(None)) | (ObjektZuschlag.gueltig_bis >= stichtag),
        )).all()
        return [ZuschlagDTO(id=z.id, bezeichnung=z.bezeichnung, art=z.art, wert=z.wert)
                for z in zeilen]


class KundePort:
    def __init__(self, session: Session, ktx: AuthKontext):
        self._session = session
        self._ktx = ktx

    def kunde(self, id: UUID) -> KundeDTO | None:
        kunde = self._session.get(Kunde, id)
        if kunde is None or kunde.tenant_id != self._ktx.tenant_id:
            return None
        return KundeDTO(id=kunde.id, tenant_id=kunde.tenant_id,
                        kundennummer=kunde.kundennummer,
                        firmenname=kunde.firmenname, aktiv=kunde.aktiv)

    def rechnungsdaten(self, kunde_id: UUID) -> RechnungsdatenDTO:
        kunde = service._lade_kunde(self._session, self._ktx, kunde_id)
        return RechnungsdatenDTO(
            kunde_id=kunde.id, firmenname=kunde.firmenname,
            zahlungsziel_tage=kunde.zahlungsziel_tage,
            skonto_prozent=kunde.skonto_prozent, skonto_tage=kunde.skonto_tage,
            rechnungsversand=kunde.rechnungsversand,
            rechnung_verdichtung=kunde.rechnung_verdichtung,
            leitweg_id=kunde.leitweg_id,
            rechnungsempfaenger_email=kunde.rechnungsempfaenger_email,
        )
