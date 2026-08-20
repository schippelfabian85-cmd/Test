"""REST-API M04: /api/v1/entgelt/… (Kernel §2) — inkl. Probe-Rechner (M04 §6)."""

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from kernel.api import benoetigt, hole_session
from kernel.auth import AuthKontext
from m01_personal.port import MitarbeiterPort
from m02_kunde_objekt.port import ObjektPort
from m04_entgelt import berechnung, service
from m04_entgelt.modelle import Feiertag, Lohnart, Lohngruppe, Tarif, Zuschlagsmaske

router = APIRouter(prefix="/api/v1/entgelt", tags=["m04-entgelt"])


def _port(session: Session, ktx: AuthKontext) -> service.EntgeltPort:
    return service.EntgeltPort(
        session, ktx,
        mitarbeiter_port=MitarbeiterPort(session, ktx),
        objekt_port=ObjektPort(session, ktx),
    )


@router.get("/tarife")
def tarife(ktx: AuthKontext = Depends(benoetigt()),
           session: Session = Depends(hole_session)) -> list[dict]:
    zeilen = session.scalars(select(Tarif).where(
        Tarif.tenant_id == ktx.tenant_id,
    ).order_by(Tarif.code, Tarif.version)).all()
    ergebnis = []
    for tarif in zeilen:
        gruppen = session.scalars(select(Lohngruppe).where(
            Lohngruppe.tarif_id == tarif.id).order_by(Lohngruppe.code)).all()
        masken = session.scalars(select(Zuschlagsmaske).where(
            Zuschlagsmaske.tarif_id == tarif.id).order_by(Zuschlagsmaske.prioritaet)).all()
        ergebnis.append({
            "id": str(tarif.id), "code": tarif.code, "version": tarif.version,
            "bezeichnung": tarif.bezeichnung, "gueltig_ab": str(tarif.gueltig_ab),
            "gueltig_bis": str(tarif.gueltig_bis) if tarif.gueltig_bis else None,
            "aktiv": tarif.aktiv,
            "lohngruppen": [{"code": g.code, "bezeichnung": g.bezeichnung,
                             "stundenlohn_cent": g.stundenlohn_cent,
                             "funktion_codes": g.funktion_codes} for g in gruppen],
            "masken": [{"id": str(m.id), "bezeichnung": m.bezeichnung,
                        "prioritaet": m.prioritaet, "kumulierung": m.kumulierung,
                        "von": str(m.von_uhrzeit), "bis": str(m.bis_uhrzeit),
                        "prozent": m.prozent, "verwendet": m.verwendet,
                        "version": m.version} for m in masken],
        })
    return ergebnis


@router.get("/lohnarten")
def lohnarten(ktx: AuthKontext = Depends(benoetigt()),
              session: Session = Depends(hole_session)) -> list[dict]:
    zeilen = session.scalars(select(Lohnart).where(
        Lohnart.tenant_id == ktx.tenant_id).order_by(Lohnart.nummer)).all()
    return [{"nummer": la.nummer, "bezeichnung": la.bezeichnung, "art": la.art,
             "steuerpflichtig": la.steuerpflichtig, "sv_pflichtig": la.sv_pflichtig,
             "aktiv": la.aktiv} for la in zeilen]


@router.get("/feiertage")
def feiertage(bundesland: str = Query("ST"), jahr: int = Query(2026),
              ktx: AuthKontext = Depends(benoetigt()),
              session: Session = Depends(hole_session)) -> list[dict]:
    zeilen = session.scalars(select(Feiertag).where(
        Feiertag.tenant_id == ktx.tenant_id,
        Feiertag.bundesland == bundesland,
    ).order_by(Feiertag.datum)).all()
    return [{"datum": str(f.datum), "bezeichnung": f.bezeichnung,
             "bundesland": f.bundesland} for f in zeilen if f.datum.year == jahr]


@router.post("/masken/{maske_id}/neue-version", status_code=201)
def maske_neue_version(maske_id: UUID, daten: dict = Body(...),
                       ktx: AuthKontext = Depends(benoetigt("ADMIN")),
                       session: Session = Depends(hole_session)) -> dict:
    gueltig_ab = date.fromisoformat(daten.pop("gueltig_ab"))
    maske = service.aendere_zuschlagsmaske(session, ktx, maske_id, gueltig_ab, **daten)
    return {"id": str(maske.id), "version": maske.version,
            "gueltig_ab": str(maske.gueltig_ab)}


@router.patch("/masken/{maske_id}")
def maske_direkt_aendern(maske_id: UUID, daten: dict = Body(...),
                         ktx: AuthKontext = Depends(benoetigt("ADMIN")),
                         session: Session = Depends(hole_session)) -> dict:
    maske = service.aendere_zuschlagsmaske_direkt(session, ktx, maske_id, **daten)
    return {"id": str(maske.id), "version": maske.version}


@router.post("/probe")
def probe_rechner(daten: dict = Body(...),
                  ktx: AuthKontext = Depends(benoetigt("ADMIN", "PLANER", "CONTROLLER")),
                  session: Session = Depends(hole_session)) -> dict:
    """Rechner zur Probe (M04 §6): Schicht eingeben, vollständige Aufschlüsselung."""
    port = _port(session, ktx)
    beginn = datetime.fromisoformat(daten["beginn_utc"])
    ende = datetime.fromisoformat(daten["ende_utc"])
    lohn = port.berechne_lohn(berechnung.LohnAnfrage(
        mitarbeiter_id=UUID(daten["mitarbeiter_id"]) if daten.get("mitarbeiter_id") else None,
        objekt_id=UUID(daten["objekt_id"]) if daten.get("objekt_id") else None,
        funktion_code=daten["funktion_code"], beginn_utc=beginn, ende_utc=ende,
        pause_minuten=int(daten.get("pause_minuten", 0)),
        bundesland=daten.get("bundesland", "ST"),
    ))
    antwort = {
        "lohn": {
            "positionen": [p.__dict__ | {"zuschlagsmaske_id": str(p.zuschlagsmaske_id)
                                         if p.zuschlagsmaske_id else None}
                           for p in lohn.positionen],
            "summe_cent": lohn.summe_cent,
            "bezahlte_minuten": lohn.bezahlte_minuten,
            "hinweise": list(lohn.hinweise),
        }
    }
    if daten.get("objekt_id"):
        umsatz = port.berechne_umsatz(berechnung.UmsatzAnfrage(
            objekt_id=UUID(daten["objekt_id"]), funktion_code=daten["funktion_code"],
            beginn_utc=beginn, ende_utc=ende,
            pause_minuten=int(daten.get("pause_minuten", 0)),
            bundesland=daten.get("bundesland", "ST"),
        ))
        antwort["umsatz"] = {
            "positionen": [p.__dict__ for p in umsatz.positionen],
            "summe_netto_cent": umsatz.summe_netto_cent,
            "minuten": umsatz.minuten,
        }
    return antwort
