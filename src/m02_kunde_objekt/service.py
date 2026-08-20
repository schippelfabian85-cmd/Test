"""Fachlogik M02 — Fachregeln R-01 bis R-08."""

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from kernel.audit import schreibe_audit
from kernel.auth import AuthKontext
from kernel.events import publiziere
from kernel.fehler import FachFehler, NichtGefunden, VersionsKonflikt
from kernel.muster import neue_version
from m02_kunde_objekt.modelle import (
    Dienstanweisung,
    DienstanweisungBestaetigung,
    Kunde,
    KundeHistorie,
    Objekt,
    ObjektMitarbeiter,
    ObjektZuschlag,
)

MODUL = "M02"


def _lade_objekt(session: Session, ktx: AuthKontext, objekt_id: UUID) -> Objekt:
    objekt = session.get(Objekt, objekt_id)
    if objekt is None or objekt.tenant_id != ktx.tenant_id:
        raise NichtGefunden("M02-E-404", "Objekt nicht gefunden", {"objekt_id": str(objekt_id)})
    return objekt


def _lade_kunde(session: Session, ktx: AuthKontext, kunde_id: UUID) -> Kunde:
    kunde = session.get(Kunde, kunde_id)
    if kunde is None or kunde.tenant_id != ktx.tenant_id:
        raise NichtGefunden("M02-E-405", "Kunde nicht gefunden", {"kunde_id": str(kunde_id)})
    return kunde


def lege_kunde_an(session: Session, ktx: AuthKontext, daten: dict) -> Kunde:
    ktx.fordere_rolle("ADMIN", "PLANER")
    for pflicht in ("kundennummer", "firmenname"):
        if not daten.get(pflicht):
            raise FachFehler("M02-E-001", "Pflichtfelder fehlen", {"felder": [pflicht]})
    if session.scalars(select(Kunde).where(
            Kunde.tenant_id == ktx.tenant_id,
            Kunde.kundennummer == daten["kundennummer"])).first():
        raise FachFehler("M02-E-003", "Kundennummer bereits vergeben",
                         {"kundennummer": daten["kundennummer"]})
    kunde = Kunde(tenant_id=ktx.tenant_id, **daten)
    session.add(kunde)
    session.flush()
    schreibe_audit(session, ktx, MODUL, "kunde", kunde.id, "ANGELEGT",
                   neu={"kundennummer": kunde.kundennummer})
    return kunde


def aendere_kunde(session: Session, ktx: AuthKontext, kunde_id: UUID,
                  aenderungen: dict, erwartete_version: int) -> Kunde:
    # Zahlungsmodalitäten nur ADMIN (M02 §8).
    zahlungsfelder = {"zahlungsziel_tage", "skonto_prozent", "skonto_tage",
                      "rechnung_verdichtung", "rechnungsversand"}
    if zahlungsfelder & set(aenderungen):
        ktx.fordere_rolle("ADMIN")
    else:
        ktx.fordere_rolle("ADMIN", "PLANER")
    kunde = _lade_kunde(session, ktx, kunde_id)
    if kunde.version != erwartete_version:
        raise VersionsKonflikt("M02-E-409", "Der Datensatz wurde zwischenzeitlich geändert",
                               {"aktuelle_version": kunde.version})
    geaendert = {}
    for feld, neu in aenderungen.items():
        if feld in {"id", "tenant_id", "kundennummer", "version"}:
            continue
        alt = getattr(kunde, feld)
        if alt != neu:
            setattr(kunde, feld, neu)
            session.add(KundeHistorie(kunde_id=kunde.id, feld=feld,
                                      alt=str(alt) if alt is not None else None,
                                      neu=str(neu) if neu is not None else None,
                                      benutzer_id=ktx.benutzer_id))
            geaendert[feld] = {"alt": alt, "neu": neu}
    if geaendert:
        kunde.version += 1
        schreibe_audit(session, ktx, MODUL, "kunde", kunde.id, "GEAENDERT",
                       alt={f: w["alt"] for f, w in geaendert.items()},
                       neu={f: w["neu"] for f, w in geaendert.items()})
    return kunde


def lege_objekt_an(session: Session, ktx: AuthKontext, daten: dict) -> Objekt:
    ktx.fordere_rolle("ADMIN", "PLANER")
    if not daten.get("kunde_id"):
        raise FachFehler("M02-E-002", "Ein Objekt braucht einen Kunden (R-01)")
    _lade_kunde(session, ktx, daten["kunde_id"])
    for pflicht in ("objektnummer", "bezeichnung"):
        if not daten.get(pflicht):
            raise FachFehler("M02-E-001", "Pflichtfelder fehlen", {"felder": [pflicht]})
    if session.scalars(select(Objekt).where(
            Objekt.tenant_id == ktx.tenant_id,
            Objekt.objektnummer == daten["objektnummer"])).first():
        raise FachFehler("M02-E-004", "Objektnummer bereits vergeben",
                         {"objektnummer": daten["objektnummer"]})
    objekt = Objekt(tenant_id=ktx.tenant_id, **daten)
    session.add(objekt)
    session.flush()
    schreibe_audit(session, ktx, MODUL, "objekt", objekt.id, "ANGELEGT",
                   neu={"objektnummer": objekt.objektnummer})
    publiziere(session, "m02.objekt.angelegt.v1", ktx.tenant_id, ktx.benutzer_id,
               {"objekt_id": str(objekt.id)})
    return objekt


def aendere_objekt(session: Session, ktx: AuthKontext, objekt_id: UUID,
                   aenderungen: dict, erwartete_version: int) -> Objekt:
    ktx.fordere_rolle("ADMIN", "PLANER")
    objekt = _lade_objekt(session, ktx, objekt_id)
    if objekt.version != erwartete_version:
        raise VersionsKonflikt("M02-E-409", "Der Datensatz wurde zwischenzeitlich geändert",
                               {"aktuelle_version": objekt.version})
    gesperrt = {"id", "tenant_id", "objektnummer", "kunde_id", "version"}
    if "kunde_id" in aenderungen and aenderungen["kunde_id"] != objekt.kunde_id:
        raise FachFehler("M02-E-006", "Ein Objekt kann nicht umgehängt werden — "
                                      "neues Objekt anlegen, altes deaktivieren (R-01)")
    geaendert = {}
    for feld, neu in aenderungen.items():
        if feld in gesperrt:
            continue
        alt = getattr(objekt, feld)
        if alt != neu:
            setattr(objekt, feld, neu)
            geaendert[feld] = {"alt": alt, "neu": neu}
    if geaendert:
        objekt.version += 1
        schreibe_audit(session, ktx, MODUL, "objekt", objekt.id, "GEAENDERT",
                       alt={f: w["alt"] for f, w in geaendert.items()},
                       neu={f: w["neu"] for f, w in geaendert.items()})
    return objekt


def deaktiviere_objekt(session: Session, ktx: AuthKontext, objekt_id: UUID,
                       schicht_lookup, pruefung_aktiv: bool = True,
                       heute: date | None = None) -> Objekt:
    """R-02/R-03: nie löschen; Deaktivierung nur ohne künftige Schichten."""
    ktx.fordere_rolle("ADMIN", "PLANER")
    objekt = _lade_objekt(session, ktx, objekt_id)
    heute = heute or date.today()
    if pruefung_aktiv and schicht_lookup is not None:
        kuenftige = [
            s for s in schicht_lookup.schichten_objekt(
                objekt_id, heute + timedelta(days=1), heute + timedelta(days=730))
            if s.zustand not in ("STORNIERT", "AUSGEFALLEN")
        ]
        if kuenftige:
            raise FachFehler("M02-E-007", "Deaktivierung nicht möglich: es liegen "
                                          "künftige Schichten vor",
                             {"anzahl_schichten": len(kuenftige)})
    objekt.aktiv = False
    schreibe_audit(session, ktx, MODUL, "objekt", objekt.id, "DEAKTIVIERT")
    publiziere(session, "m02.objekt.deaktiviert.v1", ktx.tenant_id, ktx.benutzer_id,
               {"objekt_id": str(objekt.id)})
    return objekt


def erteile_freigabe(session: Session, ktx: AuthKontext, objekt_id: UUID,
                     mitarbeiter_id: UUID, freigabe_ab: date,
                     freigabe_bis: date | None = None,
                     ist_stammkraft: bool = False) -> ObjektMitarbeiter:
    ktx.fordere_rolle("ADMIN", "PLANER")
    _lade_objekt(session, ktx, objekt_id)
    freigabe = session.get(ObjektMitarbeiter, (objekt_id, mitarbeiter_id))
    if freigabe is None:
        freigabe = ObjektMitarbeiter(objekt_id=objekt_id, mitarbeiter_id=mitarbeiter_id,
                                     freigabe_ab=freigabe_ab, freigabe_bis=freigabe_bis,
                                     ist_stammkraft=ist_stammkraft)
        session.add(freigabe)
    else:
        freigabe.freigabe_ab = freigabe_ab
        freigabe.freigabe_bis = freigabe_bis
        freigabe.ist_stammkraft = ist_stammkraft
    schreibe_audit(session, ktx, MODUL, "objekt_freigabe",
                   f"{objekt_id}/{mitarbeiter_id}", "ERTEILT",
                   neu={"ab": freigabe_ab, "bis": freigabe_bis})
    publiziere(session, "m02.objekt_freigabe.erteilt.v1", ktx.tenant_id, ktx.benutzer_id,
               {"objekt_id": str(objekt_id), "mitarbeiter_id": str(mitarbeiter_id)})
    return freigabe


def entziehe_freigabe(session: Session, ktx: AuthKontext, objekt_id: UUID,
                      mitarbeiter_id: UUID, ab: date) -> None:
    """R-05: Ablauf verhindert Neuplanung, bestehende Schichten bleiben unberührt."""
    ktx.fordere_rolle("ADMIN", "PLANER")
    freigabe = session.get(ObjektMitarbeiter, (objekt_id, mitarbeiter_id))
    if freigabe is None:
        raise NichtGefunden("M02-E-406", "Freigabe existiert nicht")
    freigabe.freigabe_bis = ab - timedelta(days=1)
    schreibe_audit(session, ktx, MODUL, "objekt_freigabe",
                   f"{objekt_id}/{mitarbeiter_id}", "ENTZOGEN", neu={"ab": ab})
    publiziere(session, "m02.objekt_freigabe.entzogen.v1", ktx.tenant_id, ktx.benutzer_id,
               {"objekt_id": str(objekt_id), "mitarbeiter_id": str(mitarbeiter_id)})


def ist_freigegeben(session: Session, objekt_id: UUID, mitarbeiter_id: UUID,
                    stichtag: date) -> bool:
    freigabe = session.get(ObjektMitarbeiter, (objekt_id, mitarbeiter_id))
    if freigabe is None:
        return False
    if stichtag < freigabe.freigabe_ab:
        return False
    return freigabe.freigabe_bis is None or stichtag <= freigabe.freigabe_bis


def veroeffentliche_dienstanweisung(session: Session, ktx: AuthKontext,
                                    objekt_id: UUID, titel: str, inhalt: str,
                                    bestaetigung_erforderlich: bool,
                                    gueltig_ab: date | None = None) -> Dienstanweisung:
    """R-06: neue Version setzt Bestätigungen zurück, wenn bestätigungspflichtig."""
    ktx.fordere_rolle("ADMIN", "PLANER")
    _lade_objekt(session, ktx, objekt_id)
    vorgaenger = session.scalars(
        select(Dienstanweisung).where(
            Dienstanweisung.objekt_id == objekt_id, Dienstanweisung.titel == titel,
        ).order_by(Dienstanweisung.version.desc())
    ).first()
    version = (vorgaenger.version + 1) if vorgaenger else 1
    anweisung = Dienstanweisung(objekt_id=objekt_id, titel=titel, inhalt=inhalt,
                                version=version, gueltig_ab=gueltig_ab,
                                bestaetigung_erforderlich=bestaetigung_erforderlich)
    session.add(anweisung)
    session.flush()
    if bestaetigung_erforderlich and vorgaenger is not None:
        session.execute(DienstanweisungBestaetigung.__table__.delete().where(
            DienstanweisungBestaetigung.dienstanweisung_id == vorgaenger.id))
    schreibe_audit(session, ktx, MODUL, "dienstanweisung", anweisung.id,
                   "VEROEFFENTLICHT", neu={"titel": titel, "version": version})
    publiziere(session, "m02.dienstanweisung.veroeffentlicht.v1", ktx.tenant_id,
               ktx.benutzer_id, {"dienstanweisung_id": str(anweisung.id)})
    return anweisung


def aendere_objekt_zuschlag(session: Session, ktx: AuthKontext, zuschlag_id: UUID,
                            gueltig_ab: date, **aenderungen) -> ObjektZuschlag:
    """R-07: Muster A; nach Verwendung in einer Abrechnung unveränderlich."""
    ktx.fordere_rolle("ADMIN")
    zuschlag = session.get(ObjektZuschlag, zuschlag_id)
    if zuschlag is None or zuschlag.tenant_id != ktx.tenant_id:
        raise NichtGefunden("M02-E-407", "Objektzuschlag nicht gefunden")
    neu = neue_version(session, zuschlag, gueltig_ab, "M02-E-011", **aenderungen)
    neu.verwendet = False
    schreibe_audit(session, ktx, MODUL, "objekt_zuschlag", neu.id, "NEUE_VERSION",
                   neu={"version": neu.version, "gueltig_ab": gueltig_ab})
    return neu


def erzeuge_wiedervorlagen_befristete(session: Session, ktx: AuthKontext,
                                      wiedervorlage_port,
                                      heute: date | None = None,
                                      vorlauf_tage: int = 30) -> int:
    """R-08: befristete Objekte erzeugen 30 Tage vor Ablauf eine Wiedervorlage."""
    heute = heute or date.today()
    befristete = session.scalars(select(Objekt).where(
        Objekt.tenant_id == ktx.tenant_id,
        Objekt.aktiv.is_(True),
        Objekt.einsatzende.is_not(None),
    )).all()
    anzahl = 0
    for objekt in befristete:
        if heute >= objekt.einsatzende - timedelta(days=vorlauf_tage):
            wiedervorlage_port.anlegen(
                tenant_id=ktx.tenant_id, bezug_typ="objekt", bezug_id=objekt.id,
                titel=f"Objekt {objekt.objektnummer} läuft am {objekt.einsatzende:%d.%m.%Y} aus",
                faellig_am=objekt.einsatzende - timedelta(days=vorlauf_tage),
            )
            anzahl += 1
    return anzahl
