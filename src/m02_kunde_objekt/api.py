"""REST-API M02: /api/v1/kunde/… und /api/v1/objekt/… (Kernel §2)."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from kernel.api import benoetigt, hole_session
from kernel.auth import AuthKontext
from kernel.zustaendigkeit import ZustaendigkeitDienst
from m02_kunde_objekt import service
from m02_kunde_objekt.modelle import Kunde, Objekt, ObjektZuschlag

router = APIRouter(prefix="/api/v1", tags=["m02-kunde-objekt"])


def _kunde_json(k: Kunde) -> dict:
    return {"id": str(k.id), "kundennummer": k.kundennummer,
            "firmenname": k.firmenname, "ort": k.ort, "aktiv": k.aktiv,
            "zahlungsziel_tage": k.zahlungsziel_tage,
            "rechnungsversand": k.rechnungsversand,
            "rechnung_verdichtung": k.rechnung_verdichtung,
            "leitweg_id": k.leitweg_id, "version": k.version}


def _objekt_json(o: Objekt) -> dict:
    return {"id": str(o.id), "objektnummer": o.objektnummer,
            "bezeichnung": o.bezeichnung, "kunde_id": str(o.kunde_id),
            "ort": o.ort, "bundesland": o.bundesland, "aktiv": o.aktiv,
            "einsatzbeginn": str(o.einsatzbeginn),
            "einsatzende": str(o.einsatzende) if o.einsatzende else None,
            "geofence_radius_meter": o.geofence_radius_meter,
            "latitude": o.latitude, "longitude": o.longitude, "version": o.version}


@router.get("/kunde/kunden")
def kunden(ktx: AuthKontext = Depends(benoetigt()),
           session: Session = Depends(hole_session)) -> list[dict]:
    zeilen = session.scalars(select(Kunde).where(
        Kunde.tenant_id == ktx.tenant_id).order_by(Kunde.kundennummer)).all()
    return [_kunde_json(k) for k in zeilen]


@router.post("/kunde/kunden", status_code=201)
def kunde_anlegen(daten: dict = Body(...),
                  ktx: AuthKontext = Depends(benoetigt("ADMIN", "PLANER")),
                  session: Session = Depends(hole_session)) -> dict:
    return _kunde_json(service.lege_kunde_an(session, ktx, daten))


@router.patch("/kunde/kunden/{kunde_id}")
def kunde_aendern(kunde_id: UUID, daten: dict = Body(...),
                  ktx: AuthKontext = Depends(benoetigt("ADMIN", "PLANER")),
                  session: Session = Depends(hole_session)) -> dict:
    version = int(daten.pop("version"))
    return _kunde_json(service.aendere_kunde(session, ktx, kunde_id, daten, version))


@router.get("/objekt/objekte")
def objekte(kunde_id: UUID | None = Query(None), nur_aktive: bool = Query(True),
            ktx: AuthKontext = Depends(benoetigt()),
            session: Session = Depends(hole_session)) -> list[dict]:
    abfrage = select(Objekt).where(Objekt.tenant_id == ktx.tenant_id)
    if kunde_id is not None:
        abfrage = abfrage.where(Objekt.kunde_id == kunde_id)
    if nur_aktive:
        abfrage = abfrage.where(Objekt.aktiv.is_(True))
    zeilen = session.scalars(abfrage.order_by(Objekt.objektnummer)).all()
    sichtbare = ZustaendigkeitDienst(session).sichtbare_objekte(ktx)
    if sichtbare is not None:
        zeilen = [o for o in zeilen if o.id in sichtbare]
    return [_objekt_json(o) for o in zeilen]


@router.post("/objekt/objekte", status_code=201)
def objekt_anlegen(daten: dict = Body(...),
                   ktx: AuthKontext = Depends(benoetigt("ADMIN", "PLANER")),
                   session: Session = Depends(hole_session)) -> dict:
    if daten.get("kunde_id"):
        daten["kunde_id"] = UUID(daten["kunde_id"])
    for feld in ("einsatzbeginn", "einsatzende"):
        if daten.get(feld):
            daten[feld] = date.fromisoformat(daten[feld])
    return _objekt_json(service.lege_objekt_an(session, ktx, daten))


@router.patch("/objekt/objekte/{objekt_id}")
def objekt_aendern(objekt_id: UUID, daten: dict = Body(...),
                   ktx: AuthKontext = Depends(benoetigt("ADMIN", "PLANER")),
                   session: Session = Depends(hole_session)) -> dict:
    version = int(daten.pop("version"))
    return _objekt_json(service.aendere_objekt(session, ktx, objekt_id, daten, version))


@router.post("/objekt/objekte/{objekt_id}/deaktivierung")
def objekt_deaktivieren(request: Request, objekt_id: UUID,
                        ktx: AuthKontext = Depends(benoetigt("ADMIN", "PLANER")),
                        session: Session = Depends(hole_session)) -> dict:
    objekt = service.deaktiviere_objekt(
        session, ktx, objekt_id,
        schicht_lookup=request.app.state.schicht_lookup,
        pruefung_aktiv=request.app.state.konfiguration.get("pruefe_schichten_bei_deaktivierung", True),
    )
    return _objekt_json(objekt)


@router.post("/objekt/objekte/{objekt_id}/freigaben", status_code=201)
def freigabe_erteilen(objekt_id: UUID, daten: dict = Body(...),
                      ktx: AuthKontext = Depends(benoetigt("ADMIN", "PLANER")),
                      session: Session = Depends(hole_session)) -> dict:
    freigabe = service.erteile_freigabe(
        session, ktx, objekt_id, UUID(daten["mitarbeiter_id"]),
        date.fromisoformat(daten["freigabe_ab"]),
        date.fromisoformat(daten["freigabe_bis"]) if daten.get("freigabe_bis") else None,
        bool(daten.get("ist_stammkraft")))
    return {"objekt_id": str(objekt_id),
            "mitarbeiter_id": daten["mitarbeiter_id"],
            "freigabe_ab": str(freigabe.freigabe_ab),
            "freigabe_bis": str(freigabe.freigabe_bis) if freigabe.freigabe_bis else None}


@router.get("/objekt/objekte/{objekt_id}/freigabe")
def freigabe_pruefen(objekt_id: UUID, mitarbeiter_id: UUID = Query(...),
                     stichtag: date = Query(...),
                     ktx: AuthKontext = Depends(benoetigt()),
                     session: Session = Depends(hole_session)) -> dict:
    return {"freigegeben": service.ist_freigegeben(session, objekt_id,
                                                   mitarbeiter_id, stichtag)}


@router.post("/objekt/objekte/{objekt_id}/dienstanweisungen", status_code=201)
def dienstanweisung(objekt_id: UUID, daten: dict = Body(...),
                    ktx: AuthKontext = Depends(benoetigt("ADMIN", "PLANER")),
                    session: Session = Depends(hole_session)) -> dict:
    anweisung = service.veroeffentliche_dienstanweisung(
        session, ktx, objekt_id, daten["titel"], daten["inhalt"],
        bool(daten.get("bestaetigung_erforderlich")))
    return {"id": str(anweisung.id), "titel": anweisung.titel,
            "version": anweisung.version}


@router.get("/objekt/objekte/{objekt_id}/zuschlaege")
def zuschlaege(objekt_id: UUID, stichtag: date = Query(...),
               ktx: AuthKontext = Depends(benoetigt()),
               session: Session = Depends(hole_session)) -> list[dict]:
    zeilen = session.scalars(select(ObjektZuschlag).where(
        ObjektZuschlag.objekt_id == objekt_id,
        ObjektZuschlag.gueltig_ab <= stichtag,
        (ObjektZuschlag.gueltig_bis.is_(None)) | (ObjektZuschlag.gueltig_bis >= stichtag),
    )).all()
    return [{"id": str(z.id), "bezeichnung": z.bezeichnung, "art": z.art,
             "wert": z.wert, "version": z.version} for z in zeilen]
