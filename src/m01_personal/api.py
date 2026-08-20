"""REST-API M01: /api/v1/personal/… (Kernel §2)."""

import csv
import io
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from kernel.api import benoetigt, hole_session
from kernel.auth import AuthKontext
from kernel.idempotenz import mit_idempotenz
from kernel.zustaendigkeit import ZustaendigkeitDienst
from m01_personal import service
from m01_personal.modelle import Mitarbeiter, MitarbeiterHistorie, Vertragstyp

router = APIRouter(prefix="/api/v1/personal", tags=["m01-personal"])


def _mitarbeiter_json(ma: Mitarbeiter, session: Session) -> dict:
    return {
        "id": str(ma.id), "personalnummer": ma.personalnummer,
        "nachname": ma.nachname, "vorname": ma.vorname,
        "geburtsdatum": str(ma.geburtsdatum), "status": ma.status,
        "eintrittsdatum": str(ma.eintrittsdatum),
        "austrittsdatum": str(ma.austrittsdatum) if ma.austrittsdatum else None,
        "vertragstyp_id": str(ma.vertragstyp_id),
        "funktion_codes": list(service.funktion_codes(session, ma.id)),
        "version": ma.version,
    }


@router.get("/mitarbeiter")
def liste(status: str | None = Query(None), funktion: str | None = Query(None),
          text: str | None = Query(None),
          ktx: AuthKontext = Depends(benoetigt()),
          session: Session = Depends(hole_session)) -> list[dict]:
    sichtbare = ZustaendigkeitDienst(session).sichtbare_personen(ktx)
    treffer = service.suche(session, ktx, status=status, funktion_code=funktion,
                            text=text, sichtbare_personen=sichtbare)
    return [_mitarbeiter_json(m, session) for m in treffer]


@router.get("/mitarbeiter.csv")
def liste_csv(status: str | None = Query(None),
              ktx: AuthKontext = Depends(benoetigt()),
              session: Session = Depends(hole_session)) -> Response:
    sichtbare = ZustaendigkeitDienst(session).sichtbare_personen(ktx)
    treffer = service.suche(session, ktx, status=status,
                            sichtbare_personen=sichtbare)
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";")
    schreiber.writerow(["Personalnummer", "Nachname", "Vorname", "Status",
                        "Eintritt", "Austritt", "Funktionen"])
    for ma in treffer:
        schreiber.writerow([ma.personalnummer, ma.nachname, ma.vorname, ma.status,
                            ma.eintrittsdatum, ma.austrittsdatum or "",
                            ",".join(service.funktion_codes(session, ma.id))])
    return Response(content=puffer.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=mitarbeiter.csv"})


@router.post("/mitarbeiter", status_code=201)
def anlegen(request: Request, daten: dict = Body(...),
            idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
            ktx: AuthKontext = Depends(benoetigt("ADMIN", "PLANER")),
            session: Session = Depends(hole_session)) -> dict:
    funktion_codes = daten.pop("funktion_codes", [])
    if daten.get("geburtsdatum"):
        daten["geburtsdatum"] = date.fromisoformat(daten["geburtsdatum"])
    if daten.get("eintrittsdatum"):
        daten["eintrittsdatum"] = date.fromisoformat(daten["eintrittsdatum"])
    if daten.get("vertragstyp_id"):
        daten["vertragstyp_id"] = UUID(daten["vertragstyp_id"])

    def aktion() -> tuple[int, dict]:
        ma = service.lege_an(session, ktx, daten, funktion_codes)
        return 201, _mitarbeiter_json(ma, session)

    _, antwort = mit_idempotenz(session, ktx, idempotency_key,
                                "POST /personal/mitarbeiter", aktion)
    return antwort


@router.get("/mitarbeiter/{mitarbeiter_id}")
def lesen(mitarbeiter_id: UUID, ktx: AuthKontext = Depends(benoetigt()),
          session: Session = Depends(hole_session)) -> dict:
    ma = service._lade(session, ktx, mitarbeiter_id)
    return _mitarbeiter_json(ma, session)


@router.patch("/mitarbeiter/{mitarbeiter_id}")
def aendern(mitarbeiter_id: UUID, daten: dict = Body(...),
            ktx: AuthKontext = Depends(benoetigt("ADMIN", "PLANER")),
            session: Session = Depends(hole_session)) -> dict:
    version = int(daten.pop("version"))
    ma = service.aendere(session, ktx, mitarbeiter_id, daten, version)
    return _mitarbeiter_json(ma, session)


@router.post("/mitarbeiter/{mitarbeiter_id}/status")
def status_setzen(mitarbeiter_id: UUID, daten: dict = Body(...),
                  ktx: AuthKontext = Depends(benoetigt("ADMIN", "PLANER")),
                  session: Session = Depends(hole_session)) -> dict:
    ma = service.setze_status(session, ktx, mitarbeiter_id, daten["status"],
                              daten.get("grund"))
    return _mitarbeiter_json(ma, session)


@router.post("/mitarbeiter/{mitarbeiter_id}/austritt")
def austritt_setzen(mitarbeiter_id: UUID, daten: dict = Body(...),
                    ktx: AuthKontext = Depends(benoetigt("ADMIN")),
                    session: Session = Depends(hole_session)) -> dict:
    ma = service.setze_austritt(session, ktx, mitarbeiter_id,
                                date.fromisoformat(daten["austrittsdatum"]),
                                daten.get("grund"))
    return _mitarbeiter_json(ma, session)


@router.post("/mitarbeiter/{mitarbeiter_id}/anonymisierung")
def anonymisieren(mitarbeiter_id: UUID, daten: dict = Body(default={}),
                  ktx: AuthKontext = Depends(benoetigt("ADMIN")),
                  session: Session = Depends(hole_session)) -> dict:
    ma = service.anonymisiere(session, ktx, mitarbeiter_id,
                              bestaetigung=bool(daten.get("bestaetigung")))
    return _mitarbeiter_json(ma, session)


@router.post("/mitarbeiter/{mitarbeiter_id}/vertragstyp")
def vertragstyp_wechseln(mitarbeiter_id: UUID, daten: dict = Body(...),
                         ktx: AuthKontext = Depends(benoetigt("ADMIN", "PLANER")),
                         session: Session = Depends(hole_session)) -> dict:
    ma = service.wechsle_vertragstyp(session, ktx, mitarbeiter_id,
                                     UUID(daten["vertragstyp_id"]),
                                     date.fromisoformat(daten["stichtag"]))
    return _mitarbeiter_json(ma, session)


@router.get("/mitarbeiter/{mitarbeiter_id}/vertragsgrenzen")
def grenzen(mitarbeiter_id: UUID, stichtag: date = Query(...),
            ktx: AuthKontext = Depends(benoetigt()),
            session: Session = Depends(hole_session)) -> dict:
    dto = service.vertragsgrenzen(session, ktx, mitarbeiter_id, stichtag)
    return dto.__dict__


@router.get("/mitarbeiter/{mitarbeiter_id}/historie")
def historie(mitarbeiter_id: UUID, ktx: AuthKontext = Depends(benoetigt()),
             session: Session = Depends(hole_session)) -> list[dict]:
    service._lade(session, ktx, mitarbeiter_id)
    zeilen = session.scalars(select(MitarbeiterHistorie).where(
        MitarbeiterHistorie.mitarbeiter_id == mitarbeiter_id,
    ).order_by(MitarbeiterHistorie.zeitpunkt.desc())).all()
    return [{"feld": z.feld, "alt": z.alt, "neu": z.neu,
             "zeitpunkt": str(z.zeitpunkt)} for z in zeilen]


@router.get("/vertragstypen")
def vertragstypen(ktx: AuthKontext = Depends(benoetigt()),
                  session: Session = Depends(hole_session)) -> list[dict]:
    zeilen = session.scalars(select(Vertragstyp).where(
        Vertragstyp.tenant_id == ktx.tenant_id,
    ).order_by(Vertragstyp.code, Vertragstyp.version)).all()
    return [{"id": str(v.id), "stamm_id": str(v.stamm_id), "version": v.version,
             "code": v.code, "bezeichnung": v.bezeichnung, "kategorie": v.kategorie,
             "gueltig_ab": str(v.gueltig_ab),
             "gueltig_bis": str(v.gueltig_bis) if v.gueltig_bis else None,
             "aktiv": v.aktiv,
             "max_verdienst_monat_cent": v.max_verdienst_monat_cent}
            for v in zeilen]
